"""§10/§11: the shared quiz/exercise state machine.

Free functions parameterized by a frozen `SessionKind` config object — not a
generic class, not two subclasses. The quiz/exercise difference is entirely
data (different ORM classes/fields, `score: float` vs `passed: bool`,
whether completion is driven), never control flow, so encoding it as
subclass overrides is exactly the mechanism that would let the two
workflows drift, which §25's shared parametrized test suite exists to
forbid. Every genuine divergence point is a named field on `QUIZ`/
`EXERCISE`, used exactly once in the engine below.

**§18.3's route table has no add/reorder-item route**, only `PATCH`/
`DELETE` on an existing item, despite §10's prose mentioning
"add/edit/delete/reorder" — the same route-table-vs-prose gap already
resolved for path items. `PATCH` doubles as reorder (via `order_index`).

**§24's error registry has no code for "follow-up before the item is
answered" or "summary read before completion"**: the former reuses
`modules.learning.question_unanswered` (same invariant — the item must be
graded first), and this file adds `modules.learning.session_not_completed`
for the latter, following the existing `session_not_draft`/
`session_not_started`/`session_completed` naming family.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from disp.core.auth import CurrentUser
from disp.core.errors import AppError
from disp.core.events import publish_after_commit
from disp.core.llm import LLMCall, LLMFacade
from disp.modules.learning import llm_schemas, prompts
from disp.modules.learning.config import get_learning_settings
from disp.modules.learning.events import PathItemCompleted
from disp.modules.learning.models import (
    ExerciseFollowup,
    ExerciseSession,
    ExerciseStep,
    ExerciseSubmission,
    PathItem,
    PathItemTopic,
    QuizAnswer,
    QuizFollowup,
    QuizQuestion,
    QuizSession,
    Topic,
    TopicTag,
)
from disp.modules.learning.service import mastery
from disp.modules.learning.service.courses import _authorize, _resolve_course
from disp.modules.learning.service.llm_errors import LLM_ERROR_TYPES, translate_llm_error
from disp.modules.learning.service.path import _resolve_path_item, load_path_item_sections

_GENERATE_QUIZ_CALL = LLMCall(
    name="learning.generate_quiz",
    schema=llm_schemas.QuizDraft,
    system=prompts.GENERATE_QUIZ_SYSTEM,
    max_output_tokens=4000,
)
_GRADE_QUIZ_CALL = LLMCall(
    name="learning.grade_quiz",
    schema=llm_schemas.QuizGrade,
    system=prompts.GRADE_QUIZ_SYSTEM,
    max_output_tokens=1000,
)
_GENERATE_EXERCISE_CALL = LLMCall(
    name="learning.generate_exercise",
    schema=llm_schemas.ExerciseDraft,
    system=prompts.GENERATE_EXERCISE_SYSTEM,
    max_output_tokens=4000,
)
_GRADE_EXERCISE_CALL = LLMCall(
    name="learning.grade_exercise",
    schema=llm_schemas.ExerciseGrade,
    system=prompts.GRADE_EXERCISE_SYSTEM,
    max_output_tokens=1000,
)
_FOLLOWUP_CALL = LLMCall(
    name="learning.followup",
    schema=None,
    system=prompts.FOLLOWUP_SYSTEM,
    max_output_tokens=1000,
)


@dataclass(frozen=True)
class SessionKind:
    name: str
    session_model: type[Any]
    item_model: type[Any]
    answer_model: type[Any]
    followup_model: type[Any]
    item_session_fk: InstrumentedAttribute[UUID]
    answer_item_fk: InstrumentedAttribute[UUID]
    followup_item_fk: InstrumentedAttribute[UUID]
    index_attr: str
    item_terminal_status: str
    generate_call: LLMCall
    grade_call: LLMCall
    generate_schema: type[BaseModel]
    grade_schema: type[BaseModel]
    min_items_setting: str
    max_items_setting: str
    draft_items: Callable[[Any], list[Any]]
    item_text: Callable[[Any], str]
    build_item: Callable[[Any, list[UUID]], dict[str, Any]]
    build_answer: Callable[[Any, list[UUID], str], dict[str, Any]]
    observed: Callable[[Any], float]
    observed_from_answer: Callable[[Any], float]
    answer_tags_for_summary: Callable[[Any, Any], list[UUID]]
    drives_completion: bool


QUIZ = SessionKind(
    name="quiz",
    session_model=QuizSession,
    item_model=QuizQuestion,
    answer_model=QuizAnswer,
    followup_model=QuizFollowup,
    item_session_fk=QuizQuestion.quiz_session_id,
    answer_item_fk=QuizAnswer.question_id,
    followup_item_fk=QuizFollowup.question_id,
    index_attr="current_question_index",
    item_terminal_status="answered",
    generate_call=_GENERATE_QUIZ_CALL,
    grade_call=_GRADE_QUIZ_CALL,
    generate_schema=llm_schemas.QuizDraft,
    grade_schema=llm_schemas.QuizGrade,
    min_items_setting="quiz_questions_min",
    max_items_setting="quiz_questions_max",
    draft_items=lambda draft: draft.questions,
    item_text=lambda item: item.question_text,
    build_item=lambda entry, tag_ids: {
        "question_text": entry.question_text,
        "target_tag_ids": tag_ids,
    },
    build_answer=lambda grade, tags_tested, text: {
        "answer_text": text,
        "score": grade.score,
        "feedback_text": grade.feedback_text,
        "tags_tested": tags_tested,
    },
    observed=lambda grade: grade.score,
    observed_from_answer=lambda answer: answer.score,
    answer_tags_for_summary=lambda answer, item: list(answer.tags_tested),
    drives_completion=True,
)

EXERCISE = SessionKind(
    name="exercise",
    session_model=ExerciseSession,
    item_model=ExerciseStep,
    answer_model=ExerciseSubmission,
    followup_model=ExerciseFollowup,
    item_session_fk=ExerciseStep.exercise_session_id,
    answer_item_fk=ExerciseSubmission.step_id,
    followup_item_fk=ExerciseFollowup.step_id,
    index_attr="current_step_index",
    item_terminal_status="submitted",
    generate_call=_GENERATE_EXERCISE_CALL,
    grade_call=_GRADE_EXERCISE_CALL,
    generate_schema=llm_schemas.ExerciseDraft,
    grade_schema=llm_schemas.ExerciseGrade,
    min_items_setting="exercise_steps_min",
    max_items_setting="exercise_steps_max",
    draft_items=lambda draft: draft.steps,
    item_text=lambda item: item.instruction_text,
    build_item=lambda entry, tag_ids: {
        "instruction_text": entry.instruction_text,
        "hint_text": entry.hint_text,
        "internal_rubric": entry.internal_rubric,
        "target_tag_ids": tag_ids,
    },
    build_answer=lambda grade, tags_tested, text: {
        "submission_text": text,
        "passed": grade.passed,
        "feedback_text": grade.feedback_text,
    },
    observed=lambda grade: 1.0 if grade.passed else 0.0,
    observed_from_answer=lambda answer: 1.0 if answer.passed else 0.0,
    # ExerciseSubmission stores no `tags_tested` column (§5.5) — the grade
    # output's own list is ephemeral, so the best available signal at
    # summary time is the step's own `target_tag_ids`.
    answer_tags_for_summary=lambda answer, item: list(item.target_tag_ids),
    drives_completion=False,
)


def _session_not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="modules.learning.session_not_found",
        title="Session not found",
        detail="The session does not exist.",
    )


def _item_not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="modules.learning.item_not_found",
        title="Item not found",
        detail="The question or step does not exist on this session.",
    )


async def _resolve_session_row(session: AsyncSession, kind: SessionKind, session_id: UUID) -> Any:
    row = await session.get(kind.session_model, session_id)
    if row is None:
        raise _session_not_found_error()
    return row


async def _authorize_via_session(
    session: AsyncSession, user: CurrentUser, sess_row: Any, action: str
) -> UUID:
    path_item = await session.get(PathItem, sess_row.path_item_id)
    if path_item is None:
        raise _session_not_found_error()
    await _resolve_course(session, path_item.course_id)
    await _authorize(session, user, path_item.course_id, action)
    return path_item.course_id


async def _current_item(session: AsyncSession, kind: SessionKind, sess_row: Any) -> Any | None:
    idx = getattr(sess_row, kind.index_attr)
    stmt = select(kind.item_model).where(
        kind.item_session_fk == sess_row.id, kind.item_model.order_index == idx
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_session_row(
    session: AsyncSession, user: CurrentUser, kind: SessionKind, session_id: UUID
) -> Any:
    """§18.3's `GET /{kind}/{session_id}` — the session header. Combined
    with `list_items` at the router boundary into the wire response, since
    the draft-editing UI needs every item, not just the current one."""
    sess_row = await _resolve_session_row(session, kind, session_id)
    await _authorize_via_session(session, user, sess_row, "read")
    return sess_row


async def list_items(session: AsyncSession, kind: SessionKind, session_id: UUID) -> list[Any]:
    stmt = (
        select(kind.item_model)
        .where(kind.item_session_fk == session_id)
        .order_by(kind.item_model.order_index)
    )
    return list((await session.execute(stmt)).scalars())


async def _available_tags_for_item(
    session: AsyncSession, path_item_id: UUID
) -> list[tuple[UUID, str]]:
    stmt = (
        select(TopicTag.id, TopicTag.name)
        .join(Topic, Topic.id == TopicTag.topic_id)
        .join(PathItemTopic, PathItemTopic.topic_id == Topic.id)
        .where(PathItemTopic.path_item_id == path_item_id)
    )
    rows = (await session.execute(stmt)).all()
    return [(tid, name) for tid, name in rows]


def _render_generate_prompt(
    content: str, tags: list[tuple[UUID, str]], min_n: int, max_n: int
) -> str:
    tag_lines = "\n".join(f"- tag_id={tid} name={name!r}" for tid, name in tags)
    return (
        f"Write between {min_n} and {max_n} items.\n\n"
        f"Available tags:\n{tag_lines}\n\n"
        f"Source content:\n{content}"
    )


def _render_grade_prompt(
    kind: SessionKind,
    item: Any,
    tag_names: dict[UUID, str],
    submitted_text: str,
    source_content: str,
) -> str:
    tags_desc = ", ".join(f"{tid} ({tag_names.get(tid, 'unknown')})" for tid in item.target_tag_ids)
    return (
        f"Item: {kind.item_text(item)}\n"
        f"Tags this item targets: {tags_desc}\n\n"
        f"Learner's response:\n{submitted_text}\n\n"
        f"Source content:\n{source_content}"
    )


def _render_followup_prompt(
    kind: SessionKind, item: Any, answer: Any, history: list[Any], content: str
) -> str:
    history_text = "\n".join(f"{h.role}: {h.content}" for h in history)
    submitted = answer.answer_text if kind.name == "quiz" else answer.submission_text
    return (
        f"Original item: {kind.item_text(item)}\n"
        f"Learner's response: {submitted}\n"
        f"Feedback given: {answer.feedback_text}\n\n"
        f"Conversation so far:\n{history_text}\n\n"
        f"New follow-up from the learner: {content}"
    )


async def create_session(
    session: AsyncSession,
    user: CurrentUser,
    llm: LLMFacade,
    kind: SessionKind,
    path_item_id: UUID,
) -> Any:
    item = await _resolve_path_item(session, path_item_id)
    await _resolve_course(session, item.course_id)
    await _authorize(session, user, item.course_id, "update")
    if item.status != "approved":
        raise AppError(
            status_code=409,
            code="modules.learning.path_not_approved",
            title="Path item not approved",
            detail="Approve the learning path before starting a session over this item.",
        )

    sections = await load_path_item_sections(session, path_item_id)
    content = "\n\n".join(f"[{s.heading_path}]\n{s.content_text}" for s in sections)
    tags = await _available_tags_for_item(session, path_item_id)
    available_ids = {tid for tid, _name in tags}

    settings = get_learning_settings()
    min_n = getattr(settings, kind.min_items_setting)
    max_n = getattr(settings, kind.max_items_setting)

    try:
        draft = cast(
            Any,
            await llm.generate(
                kind.generate_call,
                _render_generate_prompt(content, tags, min_n, max_n),
                user_id=user.id,
            ),
        )
    except LLM_ERROR_TYPES as exc:
        raise translate_llm_error(exc) from exc

    sess_row = kind.session_model(path_item_id=path_item_id, user_id=user.id, status="draft")
    session.add(sess_row)
    await session.flush()

    for i, entry in enumerate(kind.draft_items(draft)):
        filtered = [tid for tid in entry.target_tag_ids if tid in available_ids]
        item_row = kind.item_model(order_index=i, **kind.build_item(entry, filtered))
        setattr(item_row, kind.item_session_fk.key, sess_row.id)
        session.add(item_row)

    return sess_row


async def edit_item(
    session: AsyncSession,
    user: CurrentUser,
    kind: SessionKind,
    session_id: UUID,
    item_id: UUID,
    changes: dict[str, Any],
) -> Any:
    sess_row = await _resolve_session_row(session, kind, session_id)
    await _authorize_via_session(session, user, sess_row, "update")
    if sess_row.status != "draft":
        raise AppError(
            status_code=409,
            code="modules.learning.session_not_draft",
            title="Session not editable",
            detail="Items can only be edited while the session is a draft.",
        )
    item = await session.get(kind.item_model, item_id)
    if item is None or getattr(item, kind.item_session_fk.key) != sess_row.id:
        raise _item_not_found_error()
    for field, value in changes.items():
        setattr(item, field, value)
    return item


async def delete_item(
    session: AsyncSession, user: CurrentUser, kind: SessionKind, session_id: UUID, item_id: UUID
) -> None:
    sess_row = await _resolve_session_row(session, kind, session_id)
    await _authorize_via_session(session, user, sess_row, "update")
    if sess_row.status != "draft":
        raise AppError(
            status_code=409,
            code="modules.learning.session_not_draft",
            title="Session not editable",
            detail="Items can only be deleted while the session is a draft.",
        )
    item = await session.get(kind.item_model, item_id)
    if item is None or getattr(item, kind.item_session_fk.key) != sess_row.id:
        raise _item_not_found_error()
    await session.delete(item)


async def start_session(
    session: AsyncSession, user: CurrentUser, kind: SessionKind, session_id: UUID
) -> Any:
    sess_row = await _resolve_session_row(session, kind, session_id)
    await _authorize_via_session(session, user, sess_row, "update")
    if sess_row.status != "draft":
        raise AppError(
            status_code=409,
            code="modules.learning.session_not_draft",
            title="Session already started",
            detail="A session can only be started from draft.",
        )
    sess_row.status = "in_progress"
    setattr(sess_row, kind.index_attr, 0)
    sess_row.started_at = datetime.now(UTC)
    return sess_row


async def get_current_item(
    session: AsyncSession, user: CurrentUser, kind: SessionKind, session_id: UUID
) -> Any:
    sess_row = await _resolve_session_row(session, kind, session_id)
    await _authorize_via_session(session, user, sess_row, "read")
    if sess_row.status == "draft":
        raise AppError(
            status_code=409,
            code="modules.learning.session_not_started",
            title="Session not started",
            detail="Start the session before reading its current item.",
        )
    if sess_row.status == "completed":
        raise AppError(
            status_code=409,
            code="modules.learning.session_completed",
            title="Session completed",
            detail="This session has no current item; it is already completed.",
        )
    item = await _current_item(session, kind, sess_row)
    if item is None:
        raise _item_not_found_error()
    return item


async def submit_answer(
    session: AsyncSession,
    user: CurrentUser,
    llm: LLMFacade,
    kind: SessionKind,
    session_id: UUID,
    submitted_text: str,
) -> Any:
    sess_row = await _resolve_session_row(session, kind, session_id)
    await _authorize_via_session(session, user, sess_row, "update")
    if sess_row.status == "draft":
        raise AppError(
            status_code=409,
            code="modules.learning.session_not_started",
            title="Session not started",
            detail="Start the session before submitting an answer.",
        )
    if sess_row.status == "completed":
        raise AppError(
            status_code=409,
            code="modules.learning.session_completed",
            title="Session completed",
            detail="This session is already completed.",
        )
    item = await _current_item(session, kind, sess_row)
    if item is None:
        raise _item_not_found_error()
    if item.status == kind.item_terminal_status:
        raise AppError(
            status_code=409,
            code="modules.learning.question_answered",
            title="Already answered",
            detail="This item has already been graded.",
        )

    tags = await _available_tags_for_item(session, sess_row.path_item_id)
    tag_names = dict(tags)
    sections = await load_path_item_sections(session, sess_row.path_item_id)
    source_content = "\n\n".join(f"[{s.heading_path}]\n{s.content_text}" for s in sections)

    try:
        grade = cast(
            Any,
            await llm.generate(
                kind.grade_call,
                _render_grade_prompt(kind, item, tag_names, submitted_text, source_content),
                user_id=user.id,
            ),
        )
    except LLM_ERROR_TYPES as exc:
        raise translate_llm_error(exc) from exc

    target_set = set(item.target_tag_ids)
    filtered_tags_tested = [t for t in grade.tags_tested if t in target_set]

    answer_kwargs = kind.build_answer(grade, filtered_tags_tested, submitted_text)
    answer = kind.answer_model(**answer_kwargs)
    setattr(answer, kind.answer_item_fk.key, item.id)
    try:
        async with session.begin_nested():
            session.add(answer)
            await session.flush()
    except IntegrityError as exc:
        raise AppError(
            status_code=409,
            code="modules.learning.question_answered",
            title="Already answered",
            detail="This item has already been graded.",
        ) from exc

    item.status = kind.item_terminal_status

    for tag_id in filtered_tags_tested:
        await mastery.record_observation(
            session, topic_tag_id=tag_id, user_id=user.id, observed=kind.observed(grade)
        )

    return answer


async def follow_up(
    session: AsyncSession,
    user: CurrentUser,
    llm: LLMFacade,
    kind: SessionKind,
    session_id: UUID,
    content: str,
) -> Any:
    sess_row = await _resolve_session_row(session, kind, session_id)
    await _authorize_via_session(session, user, sess_row, "update")
    item = await _current_item(session, kind, sess_row)
    if item is None or item.status != kind.item_terminal_status:
        raise AppError(
            status_code=409,
            code="modules.learning.question_unanswered",
            title="Item not yet answered",
            detail="Submit an answer before following up.",
        )

    answer = (
        await session.execute(select(kind.answer_model).where(kind.answer_item_fk == item.id))
    ).scalar_one()
    history = list(
        (
            await session.execute(
                select(kind.followup_model)
                .where(kind.followup_item_fk == item.id)
                .order_by(kind.followup_model.created_at)
            )
        ).scalars()
    )

    try:
        reply = await llm.generate_text(
            _FOLLOWUP_CALL,
            _render_followup_prompt(kind, item, answer, history, content),
            user_id=user.id,
        )
    except LLM_ERROR_TYPES as exc:
        raise translate_llm_error(exc) from exc

    user_row = kind.followup_model(role="user", content=content)
    setattr(user_row, kind.followup_item_fk.key, item.id)
    session.add(user_row)

    assistant_row = kind.followup_model(role="assistant", content=reply)
    setattr(assistant_row, kind.followup_item_fk.key, item.id)
    session.add(assistant_row)
    await session.flush()
    return assistant_row


async def advance(
    session: AsyncSession, user: CurrentUser, kind: SessionKind, session_id: UUID
) -> Any:
    sess_row = await _resolve_session_row(session, kind, session_id)
    await _authorize_via_session(session, user, sess_row, "update")
    if sess_row.status == "draft":
        raise AppError(
            status_code=409,
            code="modules.learning.session_not_started",
            title="Session not started",
            detail="Start the session before advancing.",
        )
    if sess_row.status == "completed":
        raise AppError(
            status_code=409,
            code="modules.learning.session_completed",
            title="Session completed",
            detail="This session is already completed.",
        )

    item = await _current_item(session, kind, sess_row)
    if item is None or item.status != kind.item_terminal_status:
        raise AppError(
            status_code=409,
            code="modules.learning.question_unanswered",
            title="Item not yet answered",
            detail="Answer the current item before advancing.",
        )

    total = await session.scalar(
        select(func.count()).select_from(kind.item_model).where(kind.item_session_fk == sess_row.id)
    )
    new_index = getattr(sess_row, kind.index_attr) + 1
    setattr(sess_row, kind.index_attr, new_index)

    if new_index >= (total or 0):
        sess_row.status = "completed"
        sess_row.completed_at = datetime.now(UTC)
        # §3.5: only quiz completion drives path-item completion, regardless
        # of score — the single branch in this whole engine that isn't
        # uniform across kinds.
        if kind.drives_completion:
            path_item = await session.get(PathItem, sess_row.path_item_id)
            if path_item is not None:
                path_item.completion_status = "completed"
                path_item.completed_at = datetime.now(UTC)
                answers = list(
                    (
                        await session.execute(
                            select(kind.answer_model).where(
                                kind.answer_item_fk.in_(
                                    select(kind.item_model.id).where(
                                        kind.item_session_fk == sess_row.id
                                    )
                                )
                            )
                        )
                    ).scalars()
                )
                overall_score = (
                    sum(kind.observed_from_answer(a) for a in answers) / len(answers)
                    if answers
                    else 0.0
                )
                publish_after_commit(
                    session,
                    PathItemCompleted(
                        course_id=path_item.course_id,
                        path_item_id=path_item.id,
                        user_id=user.id,
                        score=overall_score,
                    ),
                )

    return sess_row


async def get_summary(
    session: AsyncSession, user: CurrentUser, kind: SessionKind, session_id: UUID
) -> dict[str, Any]:
    sess_row = await _resolve_session_row(session, kind, session_id)
    await _authorize_via_session(session, user, sess_row, "read")
    if sess_row.status != "completed":
        raise AppError(
            status_code=409,
            code="modules.learning.session_not_completed",
            title="Session not completed",
            detail="The summary is only available once the session is completed.",
        )

    items = list(
        (
            await session.execute(
                select(kind.item_model)
                .where(kind.item_session_fk == sess_row.id)
                .order_by(kind.item_model.order_index)
            )
        ).scalars()
    )
    items_by_id = {i.id: i for i in items}
    answers = list(
        (
            await session.execute(
                select(kind.answer_model).where(kind.answer_item_fk.in_(list(items_by_id)))
            )
        ).scalars()
    )

    observed_values = [kind.observed_from_answer(a) for a in answers]
    overall = sum(observed_values) / len(observed_values) if observed_values else 0.0

    per_tag: dict[UUID, list[float]] = {}
    for answer in answers:
        item = items_by_id[getattr(answer, kind.answer_item_fk.key)]
        observed = kind.observed_from_answer(answer)
        for tag_id in kind.answer_tags_for_summary(answer, item):
            per_tag.setdefault(tag_id, []).append(observed)
    tag_averages = sorted(
        ((tid, sum(vals) / len(vals)) for tid, vals in per_tag.items()), key=lambda pair: pair[1]
    )
    weakest_tag_ids = [tid for tid, _avg in tag_averages[:3]]

    return {
        "overall": overall,
        "count": len(items),
        "answers": answers,
        "weakest_tag_ids": weakest_tag_ids,
    }
