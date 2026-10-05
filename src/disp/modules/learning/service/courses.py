from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from disp.core.auth import CurrentUser, Permission, can, grant, readable_ids
from disp.core.errors import AppError
from disp.core.files import FileStore
from disp.core.pagination import Page, decode_cursor, encode_cursor
from disp.modules.learning.models import Course, Source
from disp.modules.learning.schemas import CourseCreate, CourseOut, CourseUpdate

# The `domain` this module's files live under in core.files (M18-files.md §7).
FILES_DOMAIN = "learning"

RESOURCE_TYPE = "learning.course"


def _not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="modules.learning.not_found",
        title="Course not found",
        detail="The course does not exist or is not visible to you.",
    )


def _to_out(course: Course) -> CourseOut:
    return CourseOut(
        id=course.id,
        title=course.title,
        description=course.description,
        status=course.status,
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


async def _resolve_course(session: AsyncSession, course_id: UUID) -> Course:
    course = await session.get(Course, course_id)
    if course is None or course.deleted_at is not None:
        raise _not_found_error()
    return course


async def _authorize(
    session: AsyncSession, user: CurrentUser, course_id: UUID, action: str
) -> None:
    """Resolve-then-require with existence hidden for unreadable courses
    (§19): a caller who can't read the course gets 404, never 403. A caller
    who can read it but lacks the specific permission gets 403. Every child
    entity (sources, topics, path items, sessions, notes) inherits this
    grant rather than carrying its own."""
    if await can(session, user, action, RESOURCE_TYPE, str(course_id)):
        return
    if action == "read" or not await can(session, user, "read", RESOURCE_TYPE, str(course_id)):
        raise _not_found_error()
    raise AppError(
        status_code=403,
        code="core.acl.forbidden",
        title="Forbidden",
        detail="You do not have permission to perform this action.",
    )


async def list_courses(
    session: AsyncSession,
    user: CurrentUser,
    *,
    limit: int,
    cursor: str | None,
) -> Page[CourseOut]:
    ids = await readable_ids(session, user_id=user.id, resource_type=RESOURCE_TYPE)
    if not ids:
        return Page[CourseOut](items=[], next_cursor=None, has_more=False)

    course_ids = [UUID(resource_id) for resource_id in ids]
    conditions: list[ColumnElement[bool]] = [
        Course.id.in_(course_ids),
        Course.deleted_at.is_(None),
    ]

    if cursor:
        cursor_data = decode_cursor(cursor)
        try:
            seek_id = UUID(cursor_data.id)
        except ValueError as exc:
            raise AppError(
                status_code=400,
                code="core.pagination.invalid_cursor",
                title="Invalid cursor",
                detail="The pagination cursor could not be decoded.",
            ) from exc
        seek_course = await session.get(Course, seek_id)
        if seek_course is None:
            raise AppError(
                status_code=400,
                code="core.pagination.invalid_cursor",
                title="Invalid cursor",
                detail="The pagination cursor could not be decoded.",
            )
        conditions.append(
            tuple_(Course.created_at, Course.id)
            < tuple_(literal(seek_course.created_at), literal(seek_course.id))
        )

    stmt = (
        select(Course)
        .where(*conditions)
        .order_by(Course.created_at.desc(), Course.id.desc())
        .limit(limit + 1)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars())

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return Page[CourseOut](
        items=[_to_out(row) for row in rows], next_cursor=next_cursor, has_more=has_more
    )


async def get_course(session: AsyncSession, user: CurrentUser, course_id: UUID) -> CourseOut:
    course = await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "read")
    return _to_out(course)


async def create_course(
    session: AsyncSession, user: CurrentUser, payload: CourseCreate
) -> CourseOut:
    course = Course(user_id=user.id, title=payload.title, description=payload.description)
    session.add(course)
    await session.flush()

    # Same transaction as the insert (§19): a course visible with no grant
    # yet would be an ownerless window a concurrent read could observe.
    await grant(
        session,
        resource_type=RESOURCE_TYPE,
        resource_id=str(course.id),
        user_id=user.id,
        permission=Permission.OWNER,
        granted_by=user.id,
    )

    return _to_out(course)


async def update_course(
    session: AsyncSession, user: CurrentUser, course_id: UUID, payload: CourseUpdate
) -> CourseOut:
    course = await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "update")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(course, field, value)
    course.updated_at = datetime.now(UTC)

    return _to_out(course)


async def delete_course(
    session: AsyncSession, user: CurrentUser, course_id: UUID, *, files: FileStore
) -> None:
    course = await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "delete")

    # The course is only soft-deleted and its source rows live forever, so
    # their uploaded files must be deleted explicitly or they'd stay in the
    # bucket (and billed) forever — M18-files.md §8.4.
    file_ids = await session.scalars(
        select(Source.file_id).where(Source.course_id == course_id, Source.file_id.is_not(None))
    )
    for file_id in file_ids.all():
        if file_id is not None:
            await files.delete(session, file_id, domain=FILES_DOMAIN)

    now = datetime.now(UTC)
    course.deleted_at = now
    course.updated_at = now
