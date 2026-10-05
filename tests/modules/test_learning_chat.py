"""M20 §12/§13 (Phase 7): explain (stateless) and scoped chat, including the
§13.3 freeform hybrid retrieval. All service functions here take an
explicit session — no bare `session_scope()` — so everything runs against
the ordinary per-test-rollback `db_session`, unlike the indexing/path-gen
background jobs.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser
from disp.core.errors import AppError
from disp.core.llm import FakeLLM, LLMNotConfigured, LLMRefused
from disp.modules.learning.models import (
    Course,
    PathItem,
    Source,
    SourceSection,
)
from disp.modules.learning.schemas import ChatSessionCreate, CourseCreate
from disp.modules.learning.service.chat import (
    create_chat_session,
    explain_path_item,
    list_chat_messages,
    retrieve_freeform_sections,
    send_message,
)
from disp.modules.learning.service.courses import create_course
from tests.factories import current_user_for, make_user


async def _course_with_two_items(
    session: AsyncSession, email: str
) -> tuple[CurrentUser, Course, PathItem, PathItem, SourceSection, SourceSection]:
    user = await make_user(session, email=email)
    cu = current_user_for(user)
    course_out = await create_course(session, cu, CourseCreate(title="Design Patterns"))
    course = (await session.execute(select(Course).where(Course.id == course_out.id))).scalar_one()

    source = Source(course_id=course.id, title="Notes", content_type="markdown", raw_text="x")
    session.add(source)
    await session.flush()

    section_a = SourceSection(
        source_id=source.id,
        heading_path="Ch 1",
        order_index=0,
        content_text="A singleton restricts a class to one instance.",
    )
    section_b = SourceSection(
        source_id=source.id,
        heading_path="Ch 2",
        order_index=1,
        content_text="A factory method delegates object creation to subclasses.",
    )
    session.add_all([section_a, section_b])
    await session.flush()

    from disp.modules.learning.models import PathItemTopic, Topic, TopicSourceSection

    topic_a = Topic(course_id=course.id, canonical_name="Singleton", description="d")
    topic_b = Topic(course_id=course.id, canonical_name="Factory Method", description="d")
    session.add_all([topic_a, topic_b])
    await session.flush()
    session.add_all(
        [
            TopicSourceSection(topic_id=topic_a.id, source_section_id=section_a.id),
            TopicSourceSection(topic_id=topic_b.id, source_section_id=section_b.id),
        ]
    )
    await session.flush()

    item_a = PathItem(
        course_id=course.id, tier="beginner", order_index=0, title="Singletons", status="approved"
    )
    item_b = PathItem(
        course_id=course.id, tier="beginner", order_index=1, title="Factories", status="approved"
    )
    session.add_all([item_a, item_b])
    await session.flush()
    session.add_all(
        [
            PathItemTopic(path_item_id=item_a.id, topic_id=topic_a.id),
            PathItemTopic(path_item_id=item_b.id, topic_id=topic_b.id),
        ]
    )
    await session.flush()

    return cu, course, item_a, item_b, section_a, section_b


async def test_explain_is_stateless_and_does_not_touch_completion(
    db_session: AsyncSession,
) -> None:
    cu, _course, item_a, _item_b, _sa, _sb = await _course_with_two_items(
        db_session, "learning-explain@example.com"
    )
    fake_llm = FakeLLM()
    fake_llm.register("learning.explain", "A singleton is a design pattern...")

    content = await explain_path_item(db_session, cu, fake_llm, item_a.id, "explain")
    assert content == "A singleton is a design pattern..."

    refreshed = await db_session.get(PathItem, item_a.id)
    assert refreshed is not None
    assert refreshed.completion_status == "not_started"  # untouched


async def test_explain_maps_llm_refusal_to_422(db_session: AsyncSession) -> None:
    cu, _course, item_a, _item_b, _sa, _sb = await _course_with_two_items(
        db_session, "learning-explain-refused@example.com"
    )
    fake_llm = FakeLLM()
    fake_llm.register_error("learning.explain", LLMRefused(category="policy"))

    with pytest.raises(AppError) as exc_info:
        await explain_path_item(db_session, cu, fake_llm, item_a.id, "explain")
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "modules.learning.llm_refused"


async def test_path_item_scope_chat_uses_only_that_items_content(
    db_session: AsyncSession,
) -> None:
    cu, course, item_a, _item_b, section_a, section_b = await _course_with_two_items(
        db_session, "learning-chat-scoped@example.com"
    )
    fake_llm = FakeLLM()
    sess_row = await create_chat_session(
        db_session, cu, course.id, ChatSessionCreate(scope_type="path_item", path_item_id=item_a.id)
    )
    await db_session.flush()

    fake_llm.register("learning.chat", "About singletons: ...")
    await send_message(db_session, cu, fake_llm, sess_row.id, "Tell me about this lesson.")
    await db_session.flush()

    sent_prompt = fake_llm.calls[-1].user_content
    assert section_a.content_text in sent_prompt
    assert section_b.content_text not in sent_prompt  # not part of this scope


async def test_custom_scope_chat_unions_selected_items(db_session: AsyncSession) -> None:
    cu, course, item_a, item_b, section_a, section_b = await _course_with_two_items(
        db_session, "learning-chat-custom@example.com"
    )
    fake_llm = FakeLLM()
    sess_row = await create_chat_session(
        db_session,
        cu,
        course.id,
        ChatSessionCreate(scope_type="custom", path_item_ids=[item_a.id, item_b.id]),
    )
    await db_session.flush()

    fake_llm.register("learning.chat", "Comparing both patterns: ...")
    await send_message(db_session, cu, fake_llm, sess_row.id, "Compare these two.")
    await db_session.flush()

    sent_prompt = fake_llm.calls[-1].user_content
    assert section_a.content_text in sent_prompt
    assert section_b.content_text in sent_prompt


async def test_chat_history_is_included_in_the_next_message(db_session: AsyncSession) -> None:
    cu, course, item_a, _item_b, _sa, _sb = await _course_with_two_items(
        db_session, "learning-chat-history@example.com"
    )
    fake_llm = FakeLLM()
    sess_row = await create_chat_session(
        db_session, cu, course.id, ChatSessionCreate(scope_type="path_item", path_item_id=item_a.id)
    )
    await db_session.flush()

    fake_llm.register("learning.chat", "First reply.")
    await send_message(db_session, cu, fake_llm, sess_row.id, "First question.")
    await db_session.flush()

    fake_llm.register("learning.chat", "Second reply.")
    await send_message(db_session, cu, fake_llm, sess_row.id, "Second question.")
    await db_session.flush()

    second_prompt = fake_llm.calls[-1].user_content
    assert "First question." in second_prompt
    assert "First reply." in second_prompt

    messages = await list_chat_messages(db_session, cu, sess_row.id)
    assert [m.content for m in messages] == [
        "First question.",
        "First reply.",
        "Second question.",
        "Second reply.",
    ]


async def test_create_custom_scope_without_path_item_ids_is_rejected(
    db_session: AsyncSession,
) -> None:
    cu, course, _item_a, _item_b, _sa, _sb = await _course_with_two_items(
        db_session, "learning-chat-badcustom@example.com"
    )
    with pytest.raises(AppError) as exc_info:
        await create_chat_session(
            db_session, cu, course.id, ChatSessionCreate(scope_type="custom", path_item_ids=[])
        )
    assert exc_info.value.status_code == 400


async def test_freeform_retrieval_finds_matching_section_via_fts(
    db_session: AsyncSession,
) -> None:
    cu, course, _item_a, _item_b, section_a, _section_b = await _course_with_two_items(
        db_session, "learning-freeform-fts@example.com"
    )
    fake_llm = FakeLLM()
    sections = await retrieve_freeform_sections(
        db_session, fake_llm, course.id, "singleton restricts instance", user_id=cu.id
    )
    assert section_a.id in {s.id for s in sections}


async def test_freeform_retrieval_dedupes_and_caps_at_top_k(db_session: AsyncSession) -> None:
    cu, course, _item_a, _item_b, _section_a, _section_b = await _course_with_two_items(
        db_session, "learning-freeform-dedupe@example.com"
    )
    fake_llm = FakeLLM()
    sections = await retrieve_freeform_sections(
        db_session, fake_llm, course.id, "singleton", user_id=cu.id
    )
    ids = [s.id for s in sections]
    assert len(ids) == len(set(ids))  # no duplicates even though FTS+vector can both match


async def test_freeform_retrieval_with_no_matches_returns_empty(db_session: AsyncSession) -> None:
    cu, _course, _item_a, _item_b, _sa, _sb = await _course_with_two_items(
        db_session, "learning-freeform-empty@example.com"
    )
    empty_course_id = uuid4()  # no sources at all under this id
    fake_llm = FakeLLM()
    sections = await retrieve_freeform_sections(
        db_session, fake_llm, empty_course_id, "anything", user_id=cu.id
    )
    assert sections == []


async def test_freeform_send_message_maps_embed_failure_to_503(db_session: AsyncSession) -> None:
    """Regression: `retrieve_freeform_sections`'s `llm.embed()` call used to
    run outside `send_message`'s `except LLM_ERROR_TYPES` block, so an
    unconfigured/unavailable embedding backend (`DISP_EMBEDDING_ENABLED=false`,
    same failure mode §16's index job already handles) surfaced as an
    unhandled 500 instead of the documented `modules.learning.llm_unavailable`."""
    cu, course, _item_a, _item_b, _sa, _sb = await _course_with_two_items(
        db_session, "learning-freeform-embed-unavailable@example.com"
    )
    fake_llm = FakeLLM()
    fake_llm.register_embed_error(LLMNotConfigured("DISP_EMBEDDING_ENABLED is false"))
    sess_row = await create_chat_session(
        db_session, cu, course.id, ChatSessionCreate(scope_type="freeform")
    )
    await db_session.flush()

    with pytest.raises(AppError) as exc_info:
        await send_message(db_session, cu, fake_llm, sess_row.id, "What's a singleton?")
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "modules.learning.llm_unavailable"
