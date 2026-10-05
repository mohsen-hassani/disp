"""M20 §7/§20 (Phase 8): `learning.daily_nudge`'s `notify_due`. Mirrors
`test_plants.py`'s `_platform()`/`_RecordingNotifier` idiom — `platform` is
a `SimpleNamespace(store=..., notifier=...)` carrying only what the
function actually reads.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser
from disp.core.config import get_settings
from disp.core.settings_store import SettingsStore
from disp.modules.learning.models import Course, PathItem
from disp.modules.learning.reminders import notify_due
from disp.modules.learning.schemas import CourseCreate
from disp.modules.learning.service.courses import create_course
from tests.factories import current_user_for, make_user


class _RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[UUID, str, str, str]] = []

    async def send(
        self, user_id: UUID, notification_type: str, title: str, body: str, url: str | None = None
    ) -> None:
        self.sent.append((user_id, notification_type, title, body))


def _platform(notifier: _RecordingNotifier) -> SimpleNamespace:
    store = SettingsStore(Fernet(get_settings().settings_key.get_secret_value()))
    return SimpleNamespace(store=store, notifier=notifier)


async def _active_course_with_pending_item(
    session: AsyncSession, email: str
) -> tuple[CurrentUser, Course]:
    user = await make_user(session, email=email)
    cu = current_user_for(user)
    course_out = await create_course(session, cu, CourseCreate(title="Design Patterns"))
    course = (await session.execute(select(Course).where(Course.id == course_out.id))).scalar_one()
    course.status = "active"
    item = PathItem(
        course_id=course.id, tier="beginner", order_index=0, title="Lesson", status="approved"
    )
    session.add(item)
    await session.flush()
    return cu, course


async def test_notify_due_skips_users_who_have_not_opted_in(db_session: AsyncSession) -> None:
    await _active_course_with_pending_item(db_session, "learning-nudge-optout@example.com")
    notifier = _RecordingNotifier()
    notified = await notify_due(db_session, _platform(notifier))  # type: ignore[arg-type]
    assert notified == 0
    assert notifier.sent == []


async def test_notify_due_notifies_opted_in_users_with_in_progress_courses(
    db_session: AsyncSession,
) -> None:
    cu, course = await _active_course_with_pending_item(
        db_session, "learning-nudge-optin@example.com"
    )
    store = SettingsStore(Fernet(get_settings().settings_key.get_secret_value()))
    await store.set(
        db_session, user_id=cu.id, domain="learning", key="study.daily_study_reminder", value=True
    )
    await db_session.flush()

    notifier = _RecordingNotifier()
    notified = await notify_due(db_session, _platform(notifier))  # type: ignore[arg-type]
    assert notified == 1
    assert len(notifier.sent) == 1
    user_id, notification_type, _title, body = notifier.sent[0]
    assert user_id == cu.id
    assert notification_type == "learning.study_reminder"
    assert course.title in body


async def test_notify_due_skips_courses_with_nothing_left_to_do(db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="learning-nudge-done@example.com")
    cu = current_user_for(user)
    course_out = await create_course(db_session, cu, CourseCreate(title="Finished Course"))
    course = (
        await db_session.execute(select(Course).where(Course.id == course_out.id))
    ).scalar_one()
    course.status = "active"
    item = PathItem(
        course_id=course.id,
        tier="beginner",
        order_index=0,
        title="Done",
        status="approved",
        completion_status="completed",
        completed_at=datetime.now(UTC),
    )
    db_session.add(item)
    await db_session.flush()

    store = SettingsStore(Fernet(get_settings().settings_key.get_secret_value()))
    await store.set(
        db_session, user_id=cu.id, domain="learning", key="study.daily_study_reminder", value=True
    )
    await db_session.flush()

    notifier = _RecordingNotifier()
    notified = await notify_due(db_session, _platform(notifier))  # type: ignore[arg-type]
    assert notified == 0
