"""§16: the generic `learning.job` row lifecycle — no domain logic lives
here. The orchestrator (`service/ingest.py`'s `run_index_job`, and later
`service/path.py`'s path-generation task) owns every `session_scope()` call
at each phase boundary; these functions just mutate whatever session the
caller already has open, so progress is visible before the whole job
commits (§16.2).
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser
from disp.core.errors import AppError
from disp.modules.learning.models import Job
from disp.modules.learning.schemas import JobOut
from disp.modules.learning.service.courses import _authorize, _resolve_course


def _job_not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="modules.learning.job_not_found",
        title="Job not found",
        detail="The job does not exist.",
    )


def to_job_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        course_id=job.course_id,
        kind=job.kind,
        status=job.status,
        phase=job.phase,
        progress_current=job.progress_current,
        progress_total=job.progress_total,
        error_code=job.error_code,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


async def create_job(session: AsyncSession, *, course_id: UUID, user_id: UUID, kind: str) -> Job:
    """`uq_learning_job_active` makes "one active job per course per kind" a
    database guarantee (§5.6) — a double-click is a 409, not two workers
    racing on the same topic set. The violation is caught, not pre-checked:
    a pre-check here would itself race against a concurrent create (§16).
    The nested SAVEPOINT keeps a caught violation from poisoning whatever
    outer transaction the caller is in.
    """
    job = Job(course_id=course_id, user_id=user_id, kind=kind)
    try:
        async with session.begin_nested():
            session.add(job)
            await session.flush()
    except IntegrityError as exc:
        raise AppError(
            status_code=409,
            code="modules.learning.job_already_running",
            title="A job is already running",
            detail=f"An {kind} job is already active for this course.",
        ) from exc
    return job


async def get_job(session: AsyncSession, user: CurrentUser, job_id: UUID) -> JobOut:
    job = await session.get(Job, job_id)
    if job is None:
        raise _job_not_found_error()
    await _resolve_course(session, job.course_id)
    await _authorize(session, user, job.course_id, "read")
    return to_job_out(job)


async def mark_running(session: AsyncSession, job_id: UUID) -> None:
    job = await session.get(Job, job_id)
    if job is None:
        raise _job_not_found_error()
    job.status = "running"
    job.started_at = datetime.now(UTC)


async def update_progress(
    session: AsyncSession, job_id: UUID, *, phase: str, current: int, total: int
) -> None:
    job = await session.get(Job, job_id)
    if job is None:
        raise _job_not_found_error()
    job.phase = phase
    job.progress_current = current
    job.progress_total = total


async def mark_succeeded(session: AsyncSession, job_id: UUID) -> None:
    job = await session.get(Job, job_id)
    if job is None:
        raise _job_not_found_error()
    job.status = "succeeded"
    job.finished_at = datetime.now(UTC)


async def mark_failed(session: AsyncSession, job_id: UUID, *, error_code: str) -> None:
    job = await session.get(Job, job_id)
    if job is None:
        raise _job_not_found_error()
    job.status = "failed"
    job.error_code = error_code
    job.finished_at = datetime.now(UTC)
