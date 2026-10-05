"""§12/§13: explain (stateless) and scoped chat, including §13.3's freeform
hybrid retrieval — the only two places besides §8.3's alignment fallback
that semantic search touches this module at all (§3.1).
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser
from disp.core.errors import AppError
from disp.core.llm import LLMCall, LLMFacade
from disp.modules.learning import prompts
from disp.modules.learning.config import get_learning_settings
from disp.modules.learning.models import (
    ChatMessage,
    ChatSession,
    ChatSessionScope,
    Source,
    SourceSection,
)
from disp.modules.learning.schemas import ChatSessionCreate
from disp.modules.learning.service.courses import _authorize, _resolve_course
from disp.modules.learning.service.llm_errors import LLM_ERROR_TYPES, translate_llm_error
from disp.modules.learning.service.path import (
    _resolve_path_item,
    load_path_item_sections,
)

_EXPLAIN_CALL = LLMCall(
    name="learning.explain",
    schema=None,
    system=prompts.EXPLAIN_SYSTEM,
    max_output_tokens=3000,
)
_CHAT_CALL = LLMCall(
    name="learning.chat",
    schema=None,
    system=prompts.CHAT_SYSTEM,
    max_output_tokens=2000,
)


def _render_content(sections: list[SourceSection]) -> str:
    return "\n\n".join(f"[{s.heading_path}]\n{s.content_text}" for s in sections)


async def explain_path_item(
    session: AsyncSession, user: CurrentUser, llm: LLMFacade, path_item_id: UUID, mode: str
) -> str:
    item = await _resolve_path_item(session, path_item_id)
    await _resolve_course(session, item.course_id)
    await _authorize(session, user, item.course_id, "read")

    sections = await load_path_item_sections(session, path_item_id)
    prompt = f"Mode: {mode}\n\nContent:\n{_render_content(sections)}"
    try:
        return await llm.generate_text(_EXPLAIN_CALL, prompt, user_id=user.id)
    except LLM_ERROR_TYPES as exc:
        raise translate_llm_error(exc) from exc


# --- §13: scoped chat -------------------------------------------------------


def _chat_not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="modules.learning.session_not_found",
        title="Chat session not found",
        detail="The chat session does not exist.",
    )


async def _resolve_chat_session(session: AsyncSession, chat_id: UUID) -> ChatSession:
    row = await session.get(ChatSession, chat_id)
    if row is None:
        raise _chat_not_found_error()
    return row


async def create_chat_session(
    session: AsyncSession, user: CurrentUser, course_id: UUID, payload: ChatSessionCreate
) -> ChatSession:
    await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "update")

    scope_type = payload.scope_type
    if scope_type == "path_item":
        if payload.path_item_id is None:
            raise AppError(
                status_code=400,
                code="core.platform.validation_error",
                title="Missing path_item_id",
                detail="scope_type='path_item' requires path_item_id.",
            )
        item = await _resolve_path_item(session, payload.path_item_id)
        if item.course_id != course_id:
            raise _chat_not_found_error()
        scoped_ids = [payload.path_item_id]
    elif scope_type == "custom":
        if not payload.path_item_ids:
            raise AppError(
                status_code=400,
                code="core.platform.validation_error",
                title="Missing path_item_ids",
                detail="scope_type='custom' requires at least one path_item_id.",
            )
        scoped_ids = payload.path_item_ids
        for pid in scoped_ids:
            item = await _resolve_path_item(session, pid)
            if item.course_id != course_id:
                raise _chat_not_found_error()
    else:  # freeform
        scoped_ids = []

    sess_row = ChatSession(
        course_id=course_id, user_id=user.id, scope_type=scope_type, title=payload.title
    )
    session.add(sess_row)
    await session.flush()
    session.add_all(
        ChatSessionScope(chat_session_id=sess_row.id, path_item_id=pid) for pid in scoped_ids
    )
    return sess_row


async def list_chat_sessions(
    session: AsyncSession, user: CurrentUser, course_id: UUID
) -> list[ChatSession]:
    await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "read")
    stmt = (
        select(ChatSession)
        .where(ChatSession.course_id == course_id)
        .order_by(ChatSession.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars())


async def _scope_content(session: AsyncSession, sess_row: ChatSession) -> str:
    path_item_ids = list(
        (
            await session.execute(
                select(ChatSessionScope.path_item_id).where(
                    ChatSessionScope.chat_session_id == sess_row.id
                )
            )
        ).scalars()
    )
    sections: list[SourceSection] = []
    seen: set[UUID] = set()
    for pid in path_item_ids:
        for s in await load_path_item_sections(session, pid):
            if s.id not in seen:
                seen.add(s.id)
                sections.append(s)
    return _render_content(sections)


async def _fts_candidates(
    session: AsyncSession, course_id: UUID, query: str, limit: int
) -> list[UUID]:
    tsquery = func.plainto_tsquery("simple", query)
    stmt = (
        select(SourceSection.id)
        .join(Source, Source.id == SourceSection.source_id)
        .where(Source.course_id == course_id, SourceSection.search_tsv.op("@@")(tsquery))
        .order_by(func.ts_rank(SourceSection.search_tsv, tsquery).desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def _vector_candidates(
    session: AsyncSession, course_id: UUID, query_vector: list[float], limit: int
) -> list[UUID]:
    distance = SourceSection.embedding.cosine_distance(query_vector)
    stmt = (
        select(SourceSection.id)
        .join(Source, Source.id == SourceSection.source_id)
        .where(Source.course_id == course_id, SourceSection.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def retrieve_freeform_sections(
    session: AsyncSession, llm: LLMFacade, course_id: UUID, query: str, *, user_id: UUID
) -> list[SourceSection]:
    """§13.3: FTS first (exact, cheap), pgvector second, merge-dedupe, top-k.
    The only other place semantic search appears on a read path is §8.3's
    indexing-time alignment fallback (§3.1)."""
    top_k = get_learning_settings().chat_freeform_top_k
    fts_ids = await _fts_candidates(session, course_id, query, top_k)
    [query_vector] = await llm.embed([query], user_id=user_id)
    vector_ids = await _vector_candidates(session, course_id, query_vector, top_k)

    ordered_ids: list[UUID] = []
    seen: set[UUID] = set()
    for section_id in [*fts_ids, *vector_ids]:
        if section_id not in seen:
            ordered_ids.append(section_id)
            seen.add(section_id)
    ordered_ids = ordered_ids[:top_k]
    if not ordered_ids:
        return []

    rows = (
        await session.execute(select(SourceSection).where(SourceSection.id.in_(ordered_ids)))
    ).scalars()
    by_id = {r.id: r for r in rows}
    return [by_id[i] for i in ordered_ids if i in by_id]


async def send_message(
    session: AsyncSession, user: CurrentUser, llm: LLMFacade, chat_id: UUID, content: str
) -> ChatMessage:
    sess_row = await _resolve_chat_session(session, chat_id)
    await _resolve_course(session, sess_row.course_id)
    await _authorize(session, user, sess_row.course_id, "update")

    settings = get_learning_settings()
    history = list(
        (
            await session.execute(
                select(ChatMessage)
                .where(ChatMessage.chat_session_id == sess_row.id)
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                .limit(settings.chat_history_messages)
            )
        ).scalars()
    )
    history.reverse()
    history_text = "\n".join(f"{m.role}: {m.content}" for m in history)

    try:
        if sess_row.scope_type == "freeform":
            sections = await retrieve_freeform_sections(
                session, llm, sess_row.course_id, content, user_id=user.id
            )
            scope_content = _render_content(sections)
        else:
            scope_content = await _scope_content(session, sess_row)

        prompt = (
            f"Source content:\n{scope_content}\n\n"
            f"Conversation so far:\n{history_text}\n\n"
            f"New message from the learner: {content}"
        )
        reply = await llm.generate_text(_CHAT_CALL, prompt, user_id=user.id)
    except LLM_ERROR_TYPES as exc:
        raise translate_llm_error(exc) from exc

    session.add(ChatMessage(chat_session_id=sess_row.id, role="user", content=content))
    assistant_row = ChatMessage(chat_session_id=sess_row.id, role="assistant", content=reply)
    session.add(assistant_row)
    await session.flush()
    return assistant_row


async def list_chat_messages(
    session: AsyncSession, user: CurrentUser, chat_id: UUID
) -> list[ChatMessage]:
    sess_row = await _resolve_chat_session(session, chat_id)
    await _resolve_course(session, sess_row.course_id)
    await _authorize(session, user, sess_row.course_id, "read")
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.chat_session_id == sess_row.id)
        .order_by(ChatMessage.created_at)
    )
    return list((await session.execute(stmt)).scalars())
