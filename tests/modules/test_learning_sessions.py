"""M20 §10/§11 (Phase 5/6): the shared quiz/exercise state machine.

One parametrized suite over `[QUIZ, EXERCISE]` — per §25/§12, "a divergence
between quiz and exercise must fail a test, not ship." Everything here
exercises `service/sessions.py`'s engine directly (not the HTTP routes,
which for quiz land in Phase 5 and exercise in Phase 6) since the engine
itself is where the invariant either holds or doesn't.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser
from disp.core.errors import AppError
from disp.core.llm import FakeLLM
from disp.modules.learning.llm_schemas import (
    ExerciseDraft,
    ExerciseGrade,
    ExerciseStepDraft,
    QuizDraft,
    QuizGrade,
    QuizQuestionDraft,
)
from disp.modules.learning.models import (
    Course,
    PathItem,
    PathItemTopic,
    Source,
    SourceSection,
    Topic,
    TopicSourceSection,
    TopicTag,
    TopicTagScore,
)
from disp.modules.learning.schemas import CourseCreate
from disp.modules.learning.service import sessions as sessions_service
from disp.modules.learning.service.courses import create_course
from disp.modules.learning.service.sessions import EXERCISE, QUIZ, SessionKind
from tests.factories import current_user_for, make_user

KINDS = [QUIZ, EXERCISE]


async def _approved_item_with_tag(
    session: AsyncSession, email: str
) -> tuple[CurrentUser, PathItem, TopicTag]:
    user = await make_user(session, email=email)
    cu = current_user_for(user)
    course_out = await create_course(session, cu, CourseCreate(title="Design Patterns"))
    course = (await session.execute(select(Course).where(Course.id == course_out.id))).scalar_one()

    source = Source(course_id=course.id, title="Notes", content_type="markdown", raw_text="x")
    session.add(source)
    await session.flush()
    section = SourceSection(
        source_id=source.id,
        heading_path="Ch 1",
        order_index=0,
        content_text="A singleton restricts a class to one instance.",
    )
    session.add(section)
    await session.flush()

    topic = Topic(course_id=course.id, canonical_name="Singleton", description="d")
    session.add(topic)
    await session.flush()
    session.add(TopicSourceSection(topic_id=topic.id, source_section_id=section.id))
    tag = TopicTag(topic_id=topic.id, name="explains the singleton pattern")
    session.add(tag)
    await session.flush()

    item = PathItem(
        course_id=course.id, tier="beginner", order_index=0, title="Lesson", status="approved"
    )
    session.add(item)
    await session.flush()
    session.add(PathItemTopic(path_item_id=item.id, topic_id=topic.id))
    await session.flush()

    return cu, item, tag


def _register_generate(fake_llm: FakeLLM, kind: SessionKind, tag_id: UUID, extra_tag: UUID) -> None:
    if kind is QUIZ:
        fake_llm.register(
            kind.generate_call.name,
            QuizDraft(
                questions=[
                    QuizQuestionDraft(
                        question_text="What is a singleton?", target_tag_ids=[tag_id, extra_tag]
                    )
                ]
            ),
        )
    else:
        fake_llm.register(
            kind.generate_call.name,
            ExerciseDraft(
                steps=[
                    ExerciseStepDraft(
                        instruction_text="Implement a singleton.",
                        hint_text="Use a class-level instance.",
                        internal_rubric="Must prevent more than one instance from existing.",
                        target_tag_ids=[tag_id, extra_tag],
                    )
                ]
            ),
        )


def _register_grade(fake_llm: FakeLLM, kind: SessionKind, tag_id: UUID, *, correct: bool) -> None:
    if kind is QUIZ:
        fake_llm.register(
            kind.grade_call.name,
            QuizGrade(
                score=1.0 if correct else 0.05,
                feedback_text="feedback",
                tags_tested=[tag_id],
            ),
        )
    else:
        fake_llm.register(
            kind.grade_call.name,
            ExerciseGrade(passed=correct, feedback_text="feedback", tags_tested=[tag_id]),
        )


@pytest.mark.parametrize("kind", KINDS, ids=lambda k: k.name)
async def test_create_session_drops_tag_ids_outside_the_items_topics(
    db_session: AsyncSession, kind: SessionKind
) -> None:
    cu, item, tag = await _approved_item_with_tag(
        db_session, f"learning-sessions-drop-{kind.name}@example.com"
    )
    bogus_tag_id = uuid4()
    fake_llm = FakeLLM()
    _register_generate(fake_llm, kind, tag.id, bogus_tag_id)

    sess_row = await sessions_service.create_session(db_session, cu, fake_llm, kind, item.id)
    await db_session.flush()

    items = await sessions_service.list_items(db_session, kind, sess_row.id)
    assert len(items) == 1
    assert items[0].target_tag_ids == [tag.id]  # bogus_tag_id dropped, not inserted


@pytest.mark.parametrize("kind", KINDS, ids=lambda k: k.name)
async def test_editing_is_draft_only(db_session: AsyncSession, kind: SessionKind) -> None:
    cu, item, tag = await _approved_item_with_tag(
        db_session, f"learning-sessions-editdraft-{kind.name}@example.com"
    )
    fake_llm = FakeLLM()
    _register_generate(fake_llm, kind, tag.id, uuid4())
    sess_row = await sessions_service.create_session(db_session, cu, fake_llm, kind, item.id)
    await db_session.flush()
    items = await sessions_service.list_items(db_session, kind, sess_row.id)

    await sessions_service.start_session(db_session, cu, kind, sess_row.id)
    await db_session.flush()

    with pytest.raises(AppError) as exc_info:
        await sessions_service.edit_item(
            db_session, cu, kind, sess_row.id, items[0].id, {"order_index": 0}
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "modules.learning.session_not_draft"


@pytest.mark.parametrize("kind", KINDS, ids=lambda k: k.name)
async def test_submitting_does_not_advance(db_session: AsyncSession, kind: SessionKind) -> None:
    cu, item, tag = await _approved_item_with_tag(
        db_session, f"learning-sessions-noadvance-{kind.name}@example.com"
    )
    fake_llm = FakeLLM()
    _register_generate(fake_llm, kind, tag.id, uuid4())
    sess_row = await sessions_service.create_session(db_session, cu, fake_llm, kind, item.id)
    await db_session.flush()
    await sessions_service.start_session(db_session, cu, kind, sess_row.id)
    await db_session.flush()

    _register_grade(fake_llm, kind, tag.id, correct=True)
    await sessions_service.submit_answer(db_session, cu, fake_llm, kind, sess_row.id, "my answer")
    await db_session.flush()

    refreshed = await db_session.get(kind.session_model, sess_row.id)
    assert refreshed is not None
    assert refreshed.status == "in_progress"
    assert getattr(refreshed, kind.index_attr) == 0  # unchanged


@pytest.mark.parametrize("kind", KINDS, ids=lambda k: k.name)
async def test_resubmitting_an_answered_item_conflicts(
    db_session: AsyncSession, kind: SessionKind
) -> None:
    cu, item, tag = await _approved_item_with_tag(
        db_session, f"learning-sessions-resubmit-{kind.name}@example.com"
    )
    fake_llm = FakeLLM()
    _register_generate(fake_llm, kind, tag.id, uuid4())
    sess_row = await sessions_service.create_session(db_session, cu, fake_llm, kind, item.id)
    await db_session.flush()
    await sessions_service.start_session(db_session, cu, kind, sess_row.id)
    await db_session.flush()

    _register_grade(fake_llm, kind, tag.id, correct=True)
    await sessions_service.submit_answer(db_session, cu, fake_llm, kind, sess_row.id, "first")
    await db_session.flush()

    with pytest.raises(AppError) as exc_info:
        await sessions_service.submit_answer(db_session, cu, fake_llm, kind, sess_row.id, "second")
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "modules.learning.question_answered"


@pytest.mark.parametrize("kind", KINDS, ids=lambda k: k.name)
async def test_advancing_before_answering_conflicts(
    db_session: AsyncSession, kind: SessionKind
) -> None:
    cu, item, tag = await _approved_item_with_tag(
        db_session, f"learning-sessions-earlyadvance-{kind.name}@example.com"
    )
    fake_llm = FakeLLM()
    _register_generate(fake_llm, kind, tag.id, uuid4())
    sess_row = await sessions_service.create_session(db_session, cu, fake_llm, kind, item.id)
    await db_session.flush()
    await sessions_service.start_session(db_session, cu, kind, sess_row.id)
    await db_session.flush()

    with pytest.raises(AppError) as exc_info:
        await sessions_service.advance(db_session, cu, kind, sess_row.id)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "modules.learning.question_unanswered"


@pytest.mark.parametrize("kind", KINDS, ids=lambda k: k.name)
async def test_mastery_seeds_first_observation_at_its_own_value(
    db_session: AsyncSession, kind: SessionKind
) -> None:
    cu, item, tag = await _approved_item_with_tag(
        db_session, f"learning-sessions-seed-{kind.name}@example.com"
    )
    fake_llm = FakeLLM()
    _register_generate(fake_llm, kind, tag.id, uuid4())
    sess_row = await sessions_service.create_session(db_session, cu, fake_llm, kind, item.id)
    await db_session.flush()
    await sessions_service.start_session(db_session, cu, kind, sess_row.id)
    await db_session.flush()

    _register_grade(fake_llm, kind, tag.id, correct=True)  # observed == 1.0
    await sessions_service.submit_answer(db_session, cu, fake_llm, kind, sess_row.id, "answer")
    await db_session.flush()

    score = (
        await db_session.execute(select(TopicTagScore).where(TopicTagScore.topic_tag_id == tag.id))
    ).scalar_one()
    # Seeded AT the observed value (1.0), never at alpha * observed (0.3).
    assert score.rolling_score == 1.0
    assert score.attempts_count == 1


@pytest.mark.parametrize("kind", KINDS, ids=lambda k: k.name)
async def test_completion_status_regardless_of_score_and_only_quiz_drives_it(
    db_session: AsyncSession, kind: SessionKind
) -> None:
    cu, item, tag = await _approved_item_with_tag(
        db_session, f"learning-sessions-complete-{kind.name}@example.com"
    )
    fake_llm = FakeLLM()
    _register_generate(fake_llm, kind, tag.id, uuid4())
    sess_row = await sessions_service.create_session(db_session, cu, fake_llm, kind, item.id)
    await db_session.flush()
    await sessions_service.start_session(db_session, cu, kind, sess_row.id)
    await db_session.flush()

    _register_grade(fake_llm, kind, tag.id, correct=False)  # a low/failing score
    await sessions_service.submit_answer(db_session, cu, fake_llm, kind, sess_row.id, "wrong")
    await db_session.flush()

    completed = await sessions_service.advance(db_session, cu, kind, sess_row.id)
    await db_session.flush()
    assert completed.status == "completed"
    assert completed.completed_at is not None

    refreshed_item = await db_session.get(PathItem, item.id)
    assert refreshed_item is not None
    if kind.drives_completion:
        assert refreshed_item.completion_status == "completed"  # regardless of the low score
    else:
        assert refreshed_item.completion_status == "not_started"  # exercise never touches it


@pytest.mark.parametrize("kind", KINDS, ids=lambda k: k.name)
async def test_full_session_with_followup_and_summary(
    db_session: AsyncSession, kind: SessionKind
) -> None:
    cu, item, tag = await _approved_item_with_tag(
        db_session, f"learning-sessions-full-{kind.name}@example.com"
    )
    fake_llm = FakeLLM()
    _register_generate(fake_llm, kind, tag.id, uuid4())
    sess_row = await sessions_service.create_session(db_session, cu, fake_llm, kind, item.id)
    await db_session.flush()
    await sessions_service.start_session(db_session, cu, kind, sess_row.id)
    await db_session.flush()

    _register_grade(fake_llm, kind, tag.id, correct=False)
    await sessions_service.submit_answer(db_session, cu, fake_llm, kind, sess_row.id, "wrong")
    await db_session.flush()

    fake_llm.register(sessions_service._FOLLOWUP_CALL.name, "Here's why that's not quite right.")
    reply = await sessions_service.follow_up(
        db_session, cu, fake_llm, kind, sess_row.id, "Why was that wrong?"
    )
    await db_session.flush()
    assert reply.role == "assistant"
    assert reply.content == "Here's why that's not quite right."

    completed = await sessions_service.advance(db_session, cu, kind, sess_row.id)
    await db_session.flush()
    assert completed.status == "completed"

    summary = await sessions_service.get_summary(db_session, cu, kind, sess_row.id)
    assert summary["count"] == 1
    assert len(summary["answers"]) == 1
    # A single low-scoring item makes its own tag the (only) weakest one.
    assert tag.id in summary["weakest_tag_ids"]
