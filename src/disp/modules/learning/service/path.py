"""§9: learning path generation, draft editing, and approval.

**§18.2's route table declares no dedicated "split"/"merge" endpoint**, even
though §9's prose mentions both. §18 is the authoritative route table (the
same call already made for quiz/exercise items in `service/sessions.py`), so
this file exposes only what §18.2 actually lists: `PATCH` (title, tier,
order, and — as the mechanism a client-side merge/split UI would drive —
`topic_ids` reassignment) and `DELETE`. Creating a brand-new item via a
client-side split has no route here; noted as a gap, not silently designed
around.
"""

from typing import TYPE_CHECKING, cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser
from disp.core.db import session_scope
from disp.core.errors import AppError
from disp.core.llm import LLMCall, LLMNotConfigured, LLMRefused, LLMUnavailable
from disp.modules.learning import llm_schemas, prompts
from disp.modules.learning.config import get_learning_settings
from disp.modules.learning.models import (
    Job,
    PathItem,
    PathItemTopic,
    SourceSection,
    Topic,
    TopicSourceSection,
)
from disp.modules.learning.schemas import (
    JobOut,
    PathItemContentOut,
    PathItemOut,
    PathItemUpdate,
    SourceSectionOut,
)
from disp.modules.learning.service import jobs as jobs_service
from disp.modules.learning.service.courses import _authorize, _resolve_course

if TYPE_CHECKING:
    from disp.core.platform import Platform

_GENERATE_PATH_CALL = LLMCall(
    name="learning.generate_path",
    schema=llm_schemas.LearningPathDraft,
    system=prompts.GENERATE_PATH_SYSTEM,
    max_output_tokens=6000,
)


def _path_item_not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="modules.learning.path_item_not_found",
        title="Path item not found",
        detail="The path item does not exist.",
    )


async def _resolve_path_item(session: AsyncSession, path_item_id: UUID) -> PathItem:
    item = await session.get(PathItem, path_item_id)
    if item is None:
        raise _path_item_not_found_error()
    return item


async def _topic_ids_for_item(session: AsyncSession, path_item_id: UUID) -> list[UUID]:
    rows = await session.execute(
        select(PathItemTopic.topic_id).where(PathItemTopic.path_item_id == path_item_id)
    )
    return list(rows.scalars())


async def _to_path_item_out(session: AsyncSession, item: PathItem) -> PathItemOut:
    return PathItemOut(
        id=item.id,
        course_id=item.course_id,
        tier=item.tier,
        order_index=item.order_index,
        title=item.title,
        est_minutes=item.est_minutes,
        status=item.status,
        completion_status=item.completion_status,
        completed_at=item.completed_at,
        topic_ids=await _topic_ids_for_item(session, item.id),
    )


async def load_path_item_sections(session: AsyncSession, path_item_id: UUID) -> list[SourceSection]:
    """§3.1's join: `path_item -> path_item_topic -> topic ->
    topic_source_section -> source_section`. Every runtime read of course
    content for this item — its content view, quiz/exercise generation,
    explain — goes through exactly this join, never semantic search."""
    stmt = (
        select(SourceSection)
        .join(TopicSourceSection, TopicSourceSection.source_section_id == SourceSection.id)
        .join(PathItemTopic, PathItemTopic.topic_id == TopicSourceSection.topic_id)
        .where(PathItemTopic.path_item_id == path_item_id)
        .order_by(SourceSection.source_id, SourceSection.order_index)
    )
    return list((await session.execute(stmt)).scalars())


async def get_path(session: AsyncSession, user: CurrentUser, course_id: UUID) -> list[PathItemOut]:
    await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "read")
    stmt = select(PathItem).where(PathItem.course_id == course_id).order_by(PathItem.order_index)
    rows = list((await session.execute(stmt)).scalars())
    return [await _to_path_item_out(session, row) for row in rows]


async def get_path_item_content(
    session: AsyncSession, user: CurrentUser, path_item_id: UUID
) -> PathItemContentOut:
    item = await _resolve_path_item(session, path_item_id)
    await _resolve_course(session, item.course_id)
    await _authorize(session, user, item.course_id, "read")
    sections = await load_path_item_sections(session, path_item_id)
    return PathItemContentOut(
        path_item=await _to_path_item_out(session, item),
        sections=[
            SourceSectionOut(id=s.id, heading_path=s.heading_path, content_text=s.content_text)
            for s in sections
        ],
    )


async def update_path_item(
    session: AsyncSession, user: CurrentUser, path_item_id: UUID, payload: PathItemUpdate
) -> PathItemOut:
    item = await _resolve_path_item(session, path_item_id)
    await _resolve_course(session, item.course_id)
    await _authorize(session, user, item.course_id, "update")

    changes = payload.model_dump(exclude_unset=True, exclude={"topic_ids"})
    for field, value in changes.items():
        setattr(item, field, value)

    if payload.topic_ids is not None:
        valid_ids = set(
            (
                await session.execute(select(Topic.id).where(Topic.course_id == item.course_id))
            ).scalars()
        )
        kept = [tid for tid in payload.topic_ids if tid in valid_ids]
        await session.execute(delete(PathItemTopic).where(PathItemTopic.path_item_id == item.id))
        session.add_all(PathItemTopic(path_item_id=item.id, topic_id=tid) for tid in kept)

    return await _to_path_item_out(session, item)


async def delete_path_item(session: AsyncSession, user: CurrentUser, path_item_id: UUID) -> None:
    item = await _resolve_path_item(session, path_item_id)
    await _resolve_course(session, item.course_id)
    await _authorize(session, user, item.course_id, "update")
    await session.delete(item)


async def approve_path(
    session: AsyncSession, user: CurrentUser, course_id: UUID
) -> list[PathItemOut]:
    course = await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "update")

    stmt = select(PathItem).where(PathItem.course_id == course_id).order_by(PathItem.order_index)
    items = list((await session.execute(stmt)).scalars())
    for item in items:
        item.status = "approved"
    course.status = "active"
    return [await _to_path_item_out(session, item) for item in items]


async def create_generate_path_job(
    session: AsyncSession, user: CurrentUser, course_id: UUID
) -> tuple[JobOut, str]:
    await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "update")

    has_topic = await session.scalar(select(Topic.id).where(Topic.course_id == course_id).limit(1))
    if has_topic is None:
        raise AppError(
            status_code=409,
            code="modules.learning.not_indexed",
            title="Course not indexed",
            detail="Index the course before generating a learning path.",
        )

    has_approved = await session.scalar(
        select(PathItem.id)
        .where(PathItem.course_id == course_id, PathItem.status == "approved")
        .limit(1)
    )
    if has_approved is not None:
        raise AppError(
            status_code=409,
            code="modules.learning.path_already_approved",
            title="Path already approved",
            detail="Delete the approved path before regenerating it.",
        )

    job = await jobs_service.create_job(
        session, course_id=course_id, user_id=user.id, kind="generate_path"
    )
    return jobs_service.to_job_out(job), "learning.generate_path"


async def _load_topics_for_path(session: AsyncSession, course_id: UUID) -> list[dict[str, object]]:
    stmt = (
        select(
            Topic.id,
            Topic.canonical_name,
            Topic.aggregated_summary,
            func.count(TopicSourceSection.source_section_id),
            func.coalesce(func.sum(SourceSection.token_count), 0),
        )
        .select_from(Topic)
        .outerjoin(TopicSourceSection, TopicSourceSection.topic_id == Topic.id)
        .outerjoin(SourceSection, SourceSection.id == TopicSourceSection.source_section_id)
        .where(Topic.course_id == course_id)
        .group_by(Topic.id)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "topic_id": str(topic_id),
            "canonical_name": name,
            "aggregated_summary": summary or "",
            "section_count": count,
            "total_tokens": tokens,
        }
        for topic_id, name, summary, count, tokens in rows
    ]


def _render_topics(topics: list[dict[str, object]]) -> str:
    target_minutes = get_learning_settings().target_item_minutes
    lines = [f"Target minutes per lesson: {target_minutes}"]
    for t in topics:
        lines.append(
            f"- topic_id={t['topic_id']} name={t['canonical_name']!r} "
            f"summary={t['aggregated_summary']!r} section_count={t['section_count']} "
            f"total_tokens={t['total_tokens']}"
        )
    return "\n".join(lines)


async def _generate_path(
    platform: "Platform", topics: list[dict[str, object]], *, user_id: UUID
) -> llm_schemas.LearningPathDraft:
    result = await platform.llm.generate(
        _GENERATE_PATH_CALL, _render_topics(topics), user_id=user_id
    )
    return cast(llm_schemas.LearningPathDraft, result)


async def _write_draft_path_items(
    session: AsyncSession, course_id: UUID, draft: llm_schemas.LearningPathDraft
) -> None:
    valid_ids = set(
        (await session.execute(select(Topic.id).where(Topic.course_id == course_id))).scalars()
    )
    # §9 step 5: regeneration is only reachable when no approved item exists
    # (create_generate_path_job's own guard) — so every existing item here
    # is a draft, safe to discard wholesale (cascades path_item_topic).
    await session.execute(delete(PathItem).where(PathItem.course_id == course_id))
    for i, entry in enumerate(draft.items):
        item = PathItem(
            course_id=course_id,
            tier=entry.tier,
            order_index=i,
            title=entry.title,
            est_minutes=entry.est_minutes,
        )
        session.add(item)
        await session.flush()
        kept = [tid for tid in entry.topic_ids if tid in valid_ids]
        session.add_all(PathItemTopic(path_item_id=item.id, topic_id=tid) for tid in kept)


def _map_llm_error_code(exc: Exception) -> str:
    if isinstance(exc, LLMNotConfigured | LLMUnavailable):
        return "modules.learning.llm_unavailable"
    if isinstance(exc, LLMRefused):
        return "modules.learning.llm_refused"
    return "modules.learning.path_generation_failed"


async def run_generate_path_job(platform: "Platform", job_id: UUID) -> None:
    """The `learning.generate_path` task body. Unlike indexing, this has no
    multi-phase structure: one alignment-shaped LLM call, one write — so
    it's a single working transaction bracketed by progress-only ones."""
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            raise RuntimeError(f"job {job_id} not found at run_generate_path_job start")
        course_id, user_id = job.course_id, job.user_id
        await jobs_service.mark_running(session, job_id)

    try:
        async with session_scope() as session:
            topics = await _load_topics_for_path(session, course_id)
        draft = await _generate_path(platform, topics, user_id=user_id)
        async with session_scope() as session:
            await _write_draft_path_items(session, course_id, draft)
            await jobs_service.mark_succeeded(session, job_id)
    except Exception as exc:
        async with session_scope() as session:
            await jobs_service.mark_failed(session, job_id, error_code=_map_llm_error_code(exc))
        raise
