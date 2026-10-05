from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser, current_user
from disp.core.db import get_session
from disp.core.files import FileStore, get_file_store
from disp.core.llm import LLMFacade
from disp.core.pagination import Page
from disp.core.scheduler import SchedulerFacade
from disp.core.settings_store import SettingsStore
from disp.modules.learning.schemas import (
    ChatMessageIn,
    ChatMessageOut,
    ChatSessionCreate,
    ChatSessionOut,
    CourseCreate,
    CourseOut,
    CourseUpdate,
    ExerciseItemOut,
    ExerciseItemUpdate,
    ExerciseSessionOut,
    ExerciseSubmissionIn,
    ExerciseSubmissionOut,
    ExerciseSummaryOut,
    ExplainIn,
    ExplainOut,
    FollowupIn,
    FollowupOut,
    JobOut,
    NoteCreate,
    NoteOut,
    NoteUpdate,
    PathItemContentOut,
    PathItemOut,
    PathItemUpdate,
    ProgressOut,
    QuizAnswerIn,
    QuizAnswerOut,
    QuizItemOut,
    QuizItemUpdate,
    QuizSessionOut,
    QuizSummaryOut,
    SourceOut,
    WeakPointOut,
)
from disp.modules.learning.service import chat as chat_service
from disp.modules.learning.service import courses as courses_service
from disp.modules.learning.service import ingest as ingest_service
from disp.modules.learning.service import jobs as jobs_service
from disp.modules.learning.service import mastery as mastery_service
from disp.modules.learning.service import notes as notes_service
from disp.modules.learning.service import path as path_service
from disp.modules.learning.service import sessions as sessions_service
from disp.modules.learning.service.sessions import EXERCISE, QUIZ

router = APIRouter()


def _get_scheduler(request: Request) -> SchedulerFacade:
    return request.app.state.platform.scheduler  # type: ignore[no-any-return]


def _get_llm(request: Request) -> LLMFacade:
    return request.app.state.platform.llm  # type: ignore[no-any-return]


def _get_settings_store(request: Request) -> SettingsStore:
    return request.app.state.platform.store  # type: ignore[no-any-return]


def _to_quiz_item_out(item: Any) -> QuizItemOut:
    return QuizItemOut(
        id=item.id,
        order_index=item.order_index,
        question_text=item.question_text,
        target_tag_ids=item.target_tag_ids,
        status=item.status,
    )


async def _to_quiz_session_out(session: AsyncSession, sess_row: Any) -> QuizSessionOut:
    items = await sessions_service.list_items(session, QUIZ, sess_row.id)
    return QuizSessionOut(
        id=sess_row.id,
        path_item_id=sess_row.path_item_id,
        status=sess_row.status,
        current_question_index=sess_row.current_question_index,
        created_at=sess_row.created_at,
        started_at=sess_row.started_at,
        completed_at=sess_row.completed_at,
        questions=[_to_quiz_item_out(i) for i in items],
    )


def _to_quiz_answer_out(answer: Any) -> QuizAnswerOut:
    return QuizAnswerOut(
        id=answer.id,
        question_id=answer.question_id,
        answer_text=answer.answer_text,
        score=answer.score,
        feedback_text=answer.feedback_text,
        tags_tested=answer.tags_tested,
        created_at=answer.created_at,
    )


def _to_followup_out(row: Any) -> FollowupOut:
    return FollowupOut(id=row.id, role=row.role, content=row.content, created_at=row.created_at)


def _to_exercise_item_out(item: Any) -> ExerciseItemOut:
    # Deliberately never reads item.internal_rubric onto the wire model (§3.4).
    return ExerciseItemOut(
        id=item.id,
        order_index=item.order_index,
        instruction_text=item.instruction_text,
        hint_text=item.hint_text,
        target_tag_ids=item.target_tag_ids,
        status=item.status,
    )


async def _to_exercise_session_out(session: AsyncSession, sess_row: Any) -> ExerciseSessionOut:
    items = await sessions_service.list_items(session, EXERCISE, sess_row.id)
    return ExerciseSessionOut(
        id=sess_row.id,
        path_item_id=sess_row.path_item_id,
        status=sess_row.status,
        current_step_index=sess_row.current_step_index,
        created_at=sess_row.created_at,
        started_at=sess_row.started_at,
        completed_at=sess_row.completed_at,
        steps=[_to_exercise_item_out(i) for i in items],
    )


def _to_exercise_submission_out(submission: Any) -> ExerciseSubmissionOut:
    return ExerciseSubmissionOut(
        id=submission.id,
        step_id=submission.step_id,
        submission_text=submission.submission_text,
        passed=submission.passed,
        feedback_text=submission.feedback_text,
        created_at=submission.created_at,
    )


def _to_chat_session_out(row: Any) -> ChatSessionOut:
    return ChatSessionOut(
        id=row.id,
        course_id=row.course_id,
        scope_type=row.scope_type,
        title=row.title,
        created_at=row.created_at,
    )


def _to_chat_message_out(row: Any) -> ChatMessageOut:
    return ChatMessageOut(id=row.id, role=row.role, content=row.content, created_at=row.created_at)


# Annotated to match FastAPI's `responses=` parameter type; without it mypy
# infers dict[int, dict[str, str]] and rejects every ** unpacking below.
_Responses = dict[int | str, dict[str, Any]]

_NOT_FOUND: _Responses = {404: {"description": "Course not found or not visible to the caller"}}
_FORBIDDEN: _Responses = {
    403: {"description": "Caller can see the course but lacks write permission"}
}
_SOURCE_NOT_FOUND: _Responses = {
    404: {"description": "Source not found or not visible to the caller"}
}


@router.get(
    "/courses",
    response_model=Page[CourseOut],
    status_code=200,
    summary="List the caller's courses",
    operation_id="learning_list_courses",
)
async def list_courses(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> Page[CourseOut]:
    return await courses_service.list_courses(session, user, limit=limit, cursor=cursor)


@router.post(
    "/courses",
    response_model=CourseOut,
    status_code=201,
    summary="Create a course",
    operation_id="learning_create_course",
)
async def create_course(
    payload: CourseCreate,
    response: Response,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CourseOut:
    course = await courses_service.create_course(session, user, payload)
    response.headers["Location"] = f"/api/learning/courses/{course.id}"
    return course


@router.get(
    "/courses/{course_id}",
    response_model=CourseOut,
    status_code=200,
    summary="Read a single course",
    operation_id="learning_get_course",
    responses={**_NOT_FOUND},
)
async def get_course(
    course_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CourseOut:
    return await courses_service.get_course(session, user, course_id)


@router.patch(
    "/courses/{course_id}",
    response_model=CourseOut,
    status_code=200,
    summary="Partially update a course",
    operation_id="learning_update_course",
    responses={**_NOT_FOUND, **_FORBIDDEN},
)
async def update_course(
    course_id: UUID,
    payload: CourseUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CourseOut:
    return await courses_service.update_course(session, user, course_id, payload)


@router.delete(
    "/courses/{course_id}",
    status_code=204,
    summary="Soft-delete a course",
    operation_id="learning_delete_course",
    responses={**_NOT_FOUND, **_FORBIDDEN},
)
async def delete_course(
    course_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
) -> Response:
    await courses_service.delete_course(session, user, course_id, files=files)
    return Response(status_code=204)


@router.get(
    "/courses/{course_id}/sources",
    response_model=list[SourceOut],
    status_code=200,
    summary="List a course's sources",
    operation_id="learning_list_sources",
    responses={**_NOT_FOUND},
)
async def list_sources(
    course_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[SourceOut]:
    return await ingest_service.list_sources(session, user, course_id)


@router.post(
    "/courses/{course_id}/sources",
    response_model=SourceOut,
    status_code=201,
    summary="Add a source: upload a file or paste text (§8.1)",
    operation_id="learning_create_source",
    responses={
        **_NOT_FOUND,
        **_FORBIDDEN,
        400: {"description": "The source has no extractable text (modules.learning.empty_source)"},
        409: {"description": "max_sources_per_course exceeded (modules.learning.source_limit)"},
        415: {"description": "Unrecognised content_type"},
    },
)
async def create_source(
    course_id: UUID,
    response: Response,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
    title: Annotated[str, Form()],
    content_type: Annotated[str, Form()],
    file: Annotated[UploadFile | None, File()] = None,
    raw_text: Annotated[str | None, Form()] = None,
) -> SourceOut:
    source = await ingest_service.create_source(
        session,
        user,
        course_id,
        title=title,
        content_type=content_type,
        files=files,
        file=file,
        raw_text=raw_text,
    )
    response.headers["Location"] = f"/api/learning/sources/{source.id}"
    return source


@router.delete(
    "/sources/{source_id}",
    status_code=204,
    summary="Remove a source",
    operation_id="learning_delete_source",
    responses={**_SOURCE_NOT_FOUND, **_FORBIDDEN},
)
async def delete_source(
    source_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
) -> Response:
    await ingest_service.delete_source(session, user, source_id, files=files)
    return Response(status_code=204)


@router.post(
    "/courses/{course_id}/index",
    response_model=JobOut,
    status_code=202,
    summary="Index a course: parse, align into topics, tag, summarize (§8)",
    operation_id="learning_index_course",
    responses={
        **_NOT_FOUND,
        **_FORBIDDEN,
        409: {"description": "An index job is already running for this course"},
    },
)
async def index_course(
    course_id: UUID,
    response: Response,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    scheduler: Annotated[SchedulerFacade, Depends(_get_scheduler)],
) -> JobOut:
    job, task_name = await ingest_service.create_index_job(session, user, course_id)
    # §16.2: commit the row before deferring — deferring first races the
    # worker against the transaction that creates the row it needs. This
    # forces an early commit; `get_session`'s own end-of-request commit then
    # has nothing left pending, exactly as every other write route expects.
    await session.commit()
    await scheduler.defer(task_name, job_id=str(job.id))
    response.headers["Location"] = f"/api/learning/jobs/{job.id}"
    return job


@router.get(
    "/jobs/{job_id}",
    response_model=JobOut,
    status_code=200,
    summary="Read a background job's status (§16)",
    operation_id="learning_get_job",
    responses={404: {"description": "Job not found or not visible to the caller"}},
)
async def get_job(
    job_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JobOut:
    return await jobs_service.get_job(session, user, job_id)


@router.post(
    "/courses/{course_id}/path/generate",
    response_model=JobOut,
    status_code=202,
    summary="Generate a draft learning path from the course's topic index (§9)",
    operation_id="learning_generate_path",
    responses={
        **_NOT_FOUND,
        **_FORBIDDEN,
        409: {
            "description": "Course not indexed, a job is already running, or an "
            "approved path already exists"
        },
    },
)
async def generate_path(
    course_id: UUID,
    response: Response,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    scheduler: Annotated[SchedulerFacade, Depends(_get_scheduler)],
) -> JobOut:
    job, task_name = await path_service.create_generate_path_job(session, user, course_id)
    await session.commit()  # §16.2: commit before deferring
    await scheduler.defer(task_name, job_id=str(job.id))
    response.headers["Location"] = f"/api/learning/jobs/{job.id}"
    return job


@router.get(
    "/courses/{course_id}/path",
    response_model=list[PathItemOut],
    status_code=200,
    summary="Read the course's learning path, in order (§9)",
    operation_id="learning_get_path",
    responses={**_NOT_FOUND},
)
async def get_path(
    course_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PathItemOut]:
    return await path_service.get_path(session, user, course_id)


@router.post(
    "/courses/{course_id}/path/approve",
    response_model=list[PathItemOut],
    status_code=200,
    summary="Approve the draft path: every item -> approved, course -> active (§9)",
    operation_id="learning_approve_path",
    responses={**_NOT_FOUND, **_FORBIDDEN},
)
async def approve_path(
    course_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PathItemOut]:
    return await path_service.approve_path(session, user, course_id)


_PATH_ITEM_NOT_FOUND: _Responses = {
    404: {"description": "Path item not found or not visible to the caller"}
}


@router.patch(
    "/path-items/{path_item_id}",
    response_model=PathItemOut,
    status_code=200,
    summary="Retitle, reorder, re-tier, or reassign a path item's topics (§9)",
    operation_id="learning_update_path_item",
    responses={**_PATH_ITEM_NOT_FOUND, **_FORBIDDEN},
)
async def update_path_item(
    path_item_id: UUID,
    payload: PathItemUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PathItemOut:
    return await path_service.update_path_item(session, user, path_item_id, payload)


@router.delete(
    "/path-items/{path_item_id}",
    status_code=204,
    summary="Delete a path item",
    operation_id="learning_delete_path_item",
    responses={**_PATH_ITEM_NOT_FOUND, **_FORBIDDEN},
)
async def delete_path_item(
    path_item_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await path_service.delete_path_item(session, user, path_item_id)
    return Response(status_code=204)


@router.get(
    "/path-items/{path_item_id}/content",
    response_model=PathItemContentOut,
    status_code=200,
    summary="Read a path item's joined content, via §3.1's deterministic join",
    operation_id="learning_get_path_item_content",
    responses={**_PATH_ITEM_NOT_FOUND},
)
async def get_path_item_content(
    path_item_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PathItemContentOut:
    return await path_service.get_path_item_content(session, user, path_item_id)


_SESSION_NOT_FOUND: _Responses = {
    404: {"description": "Session not found or not visible to the caller"}
}


@router.post(
    "/path-items/{path_item_id}/quizzes",
    response_model=QuizSessionOut,
    status_code=201,
    summary="Create a draft quiz over a path item (§10)",
    operation_id="learning_create_quiz",
    responses={
        **_NOT_FOUND,
        **_FORBIDDEN,
        409: {"description": "The path item is not approved (modules.learning.path_not_approved)"},
    },
)
async def create_quiz(
    path_item_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[LLMFacade, Depends(_get_llm)],
) -> QuizSessionOut:
    sess_row = await sessions_service.create_session(session, user, llm, QUIZ, path_item_id)
    await session.flush()
    return await _to_quiz_session_out(session, sess_row)


@router.get(
    "/quizzes/{session_id}",
    response_model=QuizSessionOut,
    status_code=200,
    summary="Read a quiz session and its questions (§10)",
    operation_id="learning_get_quiz",
    responses={**_SESSION_NOT_FOUND},
)
async def get_quiz(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QuizSessionOut:
    sess_row = await sessions_service.get_session_row(session, user, QUIZ, session_id)
    return await _to_quiz_session_out(session, sess_row)


@router.patch(
    "/quizzes/{session_id}/items/{item_id}",
    response_model=QuizItemOut,
    status_code=200,
    summary="Edit a draft quiz question (§10, draft only)",
    operation_id="learning_update_question",
    responses={
        **_SESSION_NOT_FOUND,
        **_FORBIDDEN,
        409: {"description": "The session is not a draft (modules.learning.session_not_draft)"},
    },
)
async def update_question(
    session_id: UUID,
    item_id: UUID,
    payload: QuizItemUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QuizItemOut:
    changes = payload.model_dump(exclude_unset=True)
    item = await sessions_service.edit_item(session, user, QUIZ, session_id, item_id, changes)
    return _to_quiz_item_out(item)


@router.delete(
    "/quizzes/{session_id}/items/{item_id}",
    status_code=204,
    summary="Delete a draft quiz question (§10, draft only)",
    operation_id="learning_delete_question",
    responses={**_SESSION_NOT_FOUND, **_FORBIDDEN},
)
async def delete_question(
    session_id: UUID,
    item_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await sessions_service.delete_item(session, user, QUIZ, session_id, item_id)
    return Response(status_code=204)


@router.post(
    "/quizzes/{session_id}/start",
    response_model=QuizSessionOut,
    status_code=200,
    summary="Start a quiz session, freezing its question set (§10)",
    operation_id="learning_start_quiz",
    responses={**_SESSION_NOT_FOUND, **_FORBIDDEN},
)
async def start_quiz(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QuizSessionOut:
    sess_row = await sessions_service.start_session(session, user, QUIZ, session_id)
    return await _to_quiz_session_out(session, sess_row)


@router.get(
    "/quizzes/{session_id}/current",
    response_model=QuizItemOut,
    status_code=200,
    summary="Read the current question, text only (§10)",
    operation_id="learning_get_current_question",
    responses={**_SESSION_NOT_FOUND},
)
async def get_current_question(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QuizItemOut:
    item = await sessions_service.get_current_item(session, user, QUIZ, session_id)
    return _to_quiz_item_out(item)


@router.post(
    "/quizzes/{session_id}/submit",
    response_model=QuizAnswerOut,
    status_code=200,
    summary="Submit an answer to the current question; does not advance (§10)",
    operation_id="learning_submit_answer",
    responses={
        **_SESSION_NOT_FOUND,
        **_FORBIDDEN,
        409: {"description": "Already answered (modules.learning.question_answered)"},
    },
)
async def submit_answer(
    session_id: UUID,
    payload: QuizAnswerIn,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[LLMFacade, Depends(_get_llm)],
) -> QuizAnswerOut:
    answer = await sessions_service.submit_answer(
        session, user, llm, QUIZ, session_id, payload.answer_text
    )
    return _to_quiz_answer_out(answer)


@router.post(
    "/quizzes/{session_id}/followup",
    response_model=FollowupOut,
    status_code=200,
    summary="Ask a free-form follow-up on the just-graded question (§10)",
    operation_id="learning_quiz_followup",
    responses={
        **_SESSION_NOT_FOUND,
        **_FORBIDDEN,
        409: {"description": "The current question is not yet answered"},
    },
)
async def quiz_followup(
    session_id: UUID,
    payload: FollowupIn,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[LLMFacade, Depends(_get_llm)],
) -> FollowupOut:
    reply = await sessions_service.follow_up(session, user, llm, QUIZ, session_id, payload.content)
    return _to_followup_out(reply)


@router.post(
    "/quizzes/{session_id}/advance",
    response_model=QuizSessionOut,
    status_code=200,
    summary="Advance past the answered question (§10)",
    operation_id="learning_advance_quiz",
    responses={
        **_SESSION_NOT_FOUND,
        **_FORBIDDEN,
        409: {"description": "The current question is not yet answered"},
    },
)
async def advance_quiz(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QuizSessionOut:
    sess_row = await sessions_service.advance(session, user, QUIZ, session_id)
    return await _to_quiz_session_out(session, sess_row)


@router.get(
    "/quizzes/{session_id}/summary",
    response_model=QuizSummaryOut,
    status_code=200,
    summary="Read a completed quiz session's summary (§10)",
    operation_id="learning_quiz_summary",
    responses={
        **_SESSION_NOT_FOUND,
        409: {
            "description": "The session is not completed (modules.learning.session_not_completed)"
        },
    },
)
async def quiz_summary(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QuizSummaryOut:
    result = await sessions_service.get_summary(session, user, QUIZ, session_id)
    return QuizSummaryOut(
        overall_score=result["overall"],
        question_count=result["count"],
        answers=[_to_quiz_answer_out(a) for a in result["answers"]],
        weakest_tag_ids=result["weakest_tag_ids"],
    )


# --- §11: exercise routes — identical shape to quiz, over EXERCISE --------


@router.post(
    "/path-items/{path_item_id}/exercises",
    response_model=ExerciseSessionOut,
    status_code=201,
    summary="Create a draft exercise over a path item (§11)",
    operation_id="learning_create_exercise",
    responses={
        **_NOT_FOUND,
        **_FORBIDDEN,
        409: {"description": "The path item is not approved (modules.learning.path_not_approved)"},
    },
)
async def create_exercise(
    path_item_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[LLMFacade, Depends(_get_llm)],
) -> ExerciseSessionOut:
    sess_row = await sessions_service.create_session(session, user, llm, EXERCISE, path_item_id)
    await session.flush()
    return await _to_exercise_session_out(session, sess_row)


@router.get(
    "/exercises/{session_id}",
    response_model=ExerciseSessionOut,
    status_code=200,
    summary="Read an exercise session and its steps (§11)",
    operation_id="learning_get_exercise",
    responses={**_SESSION_NOT_FOUND},
)
async def get_exercise(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ExerciseSessionOut:
    sess_row = await sessions_service.get_session_row(session, user, EXERCISE, session_id)
    return await _to_exercise_session_out(session, sess_row)


@router.patch(
    "/exercises/{session_id}/items/{item_id}",
    response_model=ExerciseItemOut,
    status_code=200,
    summary="Edit a draft exercise step (§11, draft only)",
    operation_id="learning_update_step",
    responses={
        **_SESSION_NOT_FOUND,
        **_FORBIDDEN,
        409: {"description": "The session is not a draft (modules.learning.session_not_draft)"},
    },
)
async def update_step(
    session_id: UUID,
    item_id: UUID,
    payload: ExerciseItemUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ExerciseItemOut:
    changes = payload.model_dump(exclude_unset=True)
    item = await sessions_service.edit_item(session, user, EXERCISE, session_id, item_id, changes)
    return _to_exercise_item_out(item)


@router.delete(
    "/exercises/{session_id}/items/{item_id}",
    status_code=204,
    summary="Delete a draft exercise step (§11, draft only)",
    operation_id="learning_delete_step",
    responses={**_SESSION_NOT_FOUND, **_FORBIDDEN},
)
async def delete_step(
    session_id: UUID,
    item_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await sessions_service.delete_item(session, user, EXERCISE, session_id, item_id)
    return Response(status_code=204)


@router.post(
    "/exercises/{session_id}/start",
    response_model=ExerciseSessionOut,
    status_code=200,
    summary="Start an exercise session, freezing its step set (§11)",
    operation_id="learning_start_exercise",
    responses={**_SESSION_NOT_FOUND, **_FORBIDDEN},
)
async def start_exercise(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ExerciseSessionOut:
    sess_row = await sessions_service.start_session(session, user, EXERCISE, session_id)
    return await _to_exercise_session_out(session, sess_row)


@router.get(
    "/exercises/{session_id}/current",
    response_model=ExerciseItemOut,
    status_code=200,
    summary="Read the current step, text only — never the rubric (§11, §3.4)",
    operation_id="learning_get_current_step",
    responses={**_SESSION_NOT_FOUND},
)
async def get_current_step(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ExerciseItemOut:
    item = await sessions_service.get_current_item(session, user, EXERCISE, session_id)
    return _to_exercise_item_out(item)


@router.post(
    "/exercises/{session_id}/submit",
    response_model=ExerciseSubmissionOut,
    status_code=200,
    summary="Submit a solution to the current step; does not advance (§11)",
    operation_id="learning_submit_step",
    responses={
        **_SESSION_NOT_FOUND,
        **_FORBIDDEN,
        409: {"description": "Already submitted (modules.learning.question_answered)"},
    },
)
async def submit_step(
    session_id: UUID,
    payload: ExerciseSubmissionIn,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[LLMFacade, Depends(_get_llm)],
) -> ExerciseSubmissionOut:
    submission = await sessions_service.submit_answer(
        session, user, llm, EXERCISE, session_id, payload.submission_text
    )
    return _to_exercise_submission_out(submission)


@router.post(
    "/exercises/{session_id}/followup",
    response_model=FollowupOut,
    status_code=200,
    summary="Ask a free-form follow-up on the just-graded step (§11)",
    operation_id="learning_exercise_followup",
    responses={
        **_SESSION_NOT_FOUND,
        **_FORBIDDEN,
        409: {"description": "The current step is not yet submitted"},
    },
)
async def exercise_followup(
    session_id: UUID,
    payload: FollowupIn,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[LLMFacade, Depends(_get_llm)],
) -> FollowupOut:
    reply = await sessions_service.follow_up(
        session, user, llm, EXERCISE, session_id, payload.content
    )
    return _to_followup_out(reply)


@router.post(
    "/exercises/{session_id}/advance",
    response_model=ExerciseSessionOut,
    status_code=200,
    summary="Advance past the submitted step (§11)",
    operation_id="learning_advance_exercise",
    responses={
        **_SESSION_NOT_FOUND,
        **_FORBIDDEN,
        409: {"description": "The current step is not yet submitted"},
    },
)
async def advance_exercise(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ExerciseSessionOut:
    sess_row = await sessions_service.advance(session, user, EXERCISE, session_id)
    return await _to_exercise_session_out(session, sess_row)


@router.get(
    "/exercises/{session_id}/summary",
    response_model=ExerciseSummaryOut,
    status_code=200,
    summary="Read a completed exercise session's summary (§11)",
    operation_id="learning_exercise_summary",
    responses={
        **_SESSION_NOT_FOUND,
        409: {
            "description": "The session is not completed (modules.learning.session_not_completed)"
        },
    },
)
async def exercise_summary(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ExerciseSummaryOut:
    result = await sessions_service.get_summary(session, user, EXERCISE, session_id)
    pass_count = sum(1 for a in result["answers"] if a.passed)
    pass_rate = pass_count / result["count"] if result["count"] else 0.0
    return ExerciseSummaryOut(
        pass_rate=pass_rate,
        step_count=result["count"],
        submissions=[_to_exercise_submission_out(a) for a in result["answers"]],
        weakest_tag_ids=result["weakest_tag_ids"],
    )


# --- §12: explain ----------------------------------------------------------


@router.post(
    "/path-items/{path_item_id}/explain",
    response_model=ExplainOut,
    status_code=200,
    summary="Explain, guide, or summarize a path item — stateless (§12)",
    operation_id="learning_explain_path_item",
    responses={
        **_PATH_ITEM_NOT_FOUND,
        422: {"description": "The model declined to respond (modules.learning.llm_refused)"},
        503: {
            "description": "AI features are temporarily unavailable "
            "(modules.learning.llm_unavailable)"
        },
    },
)
async def explain_path_item(
    path_item_id: UUID,
    payload: ExplainIn,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[LLMFacade, Depends(_get_llm)],
) -> ExplainOut:
    content = await chat_service.explain_path_item(session, user, llm, path_item_id, payload.mode)
    return ExplainOut(content=content)


# --- §13: scoped chat --------------------------------------------------------


@router.post(
    "/courses/{course_id}/chats",
    response_model=ChatSessionOut,
    status_code=201,
    summary="Create a scoped chat session (§13)",
    operation_id="learning_create_chat",
    responses={**_NOT_FOUND, **_FORBIDDEN},
)
async def create_chat(
    course_id: UUID,
    payload: ChatSessionCreate,
    response: Response,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatSessionOut:
    row = await chat_service.create_chat_session(session, user, course_id, payload)
    await session.flush()
    response.headers["Location"] = f"/api/learning/chats/{row.id}"
    return _to_chat_session_out(row)


@router.get(
    "/courses/{course_id}/chats",
    response_model=list[ChatSessionOut],
    status_code=200,
    summary="List a course's chat sessions (§13)",
    operation_id="learning_list_chats",
    responses={**_NOT_FOUND},
)
async def list_chats(
    course_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ChatSessionOut]:
    rows = await chat_service.list_chat_sessions(session, user, course_id)
    return [_to_chat_session_out(r) for r in rows]


_CHAT_NOT_FOUND: _Responses = {
    404: {"description": "Chat session not found or not visible to the caller"}
}


@router.get(
    "/chats/{chat_id}/messages",
    response_model=list[ChatMessageOut],
    status_code=200,
    summary="List a chat session's messages, oldest first (§13)",
    operation_id="learning_list_chat_messages",
    responses={**_CHAT_NOT_FOUND},
)
async def list_chat_messages(
    chat_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ChatMessageOut]:
    rows = await chat_service.list_chat_messages(session, user, chat_id)
    return [_to_chat_message_out(r) for r in rows]


@router.post(
    "/chats/{chat_id}/messages",
    response_model=ChatMessageOut,
    status_code=200,
    summary="Send a chat message; returns the assistant's reply (§13)",
    operation_id="learning_send_chat_message",
    responses={
        **_CHAT_NOT_FOUND,
        **_FORBIDDEN,
        422: {"description": "The model declined to respond (modules.learning.llm_refused)"},
        503: {
            "description": "AI features are temporarily unavailable "
            "(modules.learning.llm_unavailable)"
        },
    },
)
async def send_chat_message(
    chat_id: UUID,
    payload: ChatMessageIn,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[LLMFacade, Depends(_get_llm)],
) -> ChatMessageOut:
    reply = await chat_service.send_message(session, user, llm, chat_id, payload.content)
    return _to_chat_message_out(reply)


# --- §14: notes --------------------------------------------------------


@router.get(
    "/courses/{course_id}/notes",
    response_model=Page[NoteOut],
    status_code=200,
    summary="List a course's notes, filterable by label and anchor (§14)",
    operation_id="learning_list_notes",
    responses={**_NOT_FOUND},
)
async def list_notes(
    course_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    label: Annotated[str | None, Query()] = None,
    path_item_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> Page[NoteOut]:
    return await notes_service.list_notes(
        session,
        user,
        course_id,
        label=label,
        path_item_id=path_item_id,
        limit=limit,
        cursor=cursor,
    )


@router.post(
    "/courses/{course_id}/notes",
    response_model=NoteOut,
    status_code=201,
    summary="Create a note, optionally anchored to a path item, topic, or section (§14)",
    operation_id="learning_create_note",
    responses={
        **_NOT_FOUND,
        **_FORBIDDEN,
        400: {
            "description": "More than one anchor supplied (modules.learning.invalid_note_anchor)"
        },
    },
)
async def create_note(
    course_id: UUID,
    payload: NoteCreate,
    response: Response,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteOut:
    note = await notes_service.create_note(session, user, course_id, payload)
    response.headers["Location"] = f"/api/learning/notes/{note.id}"
    return note


_NOTE_NOT_FOUND: _Responses = {404: {"description": "Note not found or not visible to the caller"}}


@router.patch(
    "/notes/{note_id}",
    response_model=NoteOut,
    status_code=200,
    summary="Update a note's label or body",
    operation_id="learning_update_note",
    responses={**_NOTE_NOT_FOUND, **_FORBIDDEN},
)
async def update_note(
    note_id: UUID,
    payload: NoteUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteOut:
    return await notes_service.update_note(session, user, note_id, payload)


@router.delete(
    "/notes/{note_id}",
    status_code=204,
    summary="Soft-delete a note",
    operation_id="learning_delete_note",
    responses={**_NOTE_NOT_FOUND, **_FORBIDDEN},
)
async def delete_note(
    note_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await notes_service.delete_note(session, user, note_id)
    return Response(status_code=204)


# --- §15.2/§15.3: progress and weak points ----------------------------------


@router.get(
    "/courses/{course_id}/progress",
    response_model=ProgressOut,
    status_code=200,
    summary="Completed vs. total approved path items, by tier (§15.2)",
    operation_id="learning_get_progress",
    responses={**_NOT_FOUND},
)
async def get_progress(
    course_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProgressOut:
    return await mastery_service.get_progress(session, user, course_id)


@router.get(
    "/courses/{course_id}/weak-points",
    response_model=list[WeakPointOut],
    status_code=200,
    summary="Tags below the weak-point threshold, weakest first (§15.3)",
    operation_id="learning_get_weak_points",
    responses={**_NOT_FOUND},
)
async def get_weak_points(
    course_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    store: Annotated[SettingsStore, Depends(_get_settings_store)],
) -> list[WeakPointOut]:
    return await mastery_service.get_weak_points(session, user, store, course_id)
