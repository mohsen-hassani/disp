from typing import ClassVar
from uuid import uuid4

import pytest
import structlog.testing
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core import notifier as notifier_module
from disp.core.models import NotificationLog
from disp.core.scheduler import SchedulerFacade
from disp.core.scheduler import app as procrastinate_app
from disp.core.settings_store import SettingsStore
from tests.factories import make_user

SECRET_URL = "https://hooks.example.com/services/T00/B00/super-secret-webhook-token"  # noqa: S105


class _FakeRegistry:
    def __init__(self, notification_types: dict[str, object]) -> None:
        self.notification_types = notification_types


class _FakeApprise:
    """Stand-in for apprise.Apprise: records adds, always "delivers" OK."""

    instances: ClassVar[list["_FakeApprise"]] = []

    def __init__(self) -> None:
        self.targets: dict[str, str] = {}
        _FakeApprise.instances.append(self)

    def add(self, url: str, tag: str) -> None:
        self.targets[tag] = url

    async def async_notify(self, *, title: str, body: str, tag: str) -> bool:
        return True


@pytest.fixture(autouse=True)
def _reset_fake_apprise() -> None:
    _FakeApprise.instances.clear()
    yield
    _FakeApprise.instances.clear()


def _configure(session_maker: async_sessionmaker[AsyncSession], notification_types: dict) -> None:
    fernet = Fernet(Fernet.generate_key())
    notifier_module.configure(
        store=SettingsStore(fernet),
        session_maker=session_maker,
        registry=_FakeRegistry(notification_types),
    )


# Case 38: `send` with an unknown notification type raises ValueError.


async def test_send_unknown_notification_type_raises_value_error(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _configure(session_maker, {})
    facade = notifier_module.NotifierFacade(SchedulerFacade(procrastinate_app))

    with pytest.raises(ValueError, match="unknown notification type"):
        await facade.send(uuid4(), "notes.reminder", "title", "body")


# Case 39: delivery with no configured channels writes status='no_channels'
# and does not raise.


async def test_delivery_with_no_channels_writes_no_channels_status(
    db_session: AsyncSession, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    user = await make_user(db_session, email="notif-nochan@example.com")
    _configure(session_maker, {"notes.reminder": object()})

    await notifier_module._deliver_notification(
        user_id=str(user.id), notification_type="notes.reminder", title="Hi", body="Body"
    )

    row = (
        await db_session.execute(select(NotificationLog).where(NotificationLog.user_id == user.id))
    ).scalar_one()
    assert row.status == "no_channels"
    assert row.channel_ids == []


# Case 40: delivery calls Apprise with the decrypted URLs and logs status='sent'.


async def test_delivery_calls_apprise_with_decrypted_urls_and_logs_sent(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notifier_module.apprise, "Apprise", _FakeApprise)
    user = await make_user(db_session, email="notif-sent@example.com")
    _configure(session_maker, {"notes.reminder": object()})

    store = notifier_module._context.store  # type: ignore[union-attr]
    await store.set(
        db_session,
        user_id=user.id,
        domain="core",
        key="notifier.channels",
        value=[{"id": "chan1", "label": "Chan 1", "enabled": True}],
    )
    await store.set(
        db_session,
        user_id=user.id,
        domain="core",
        key="notifier.urls",
        value={"chan1": SECRET_URL},
        is_secret=True,
    )
    await db_session.commit()

    await notifier_module._deliver_notification(
        user_id=str(user.id), notification_type="notes.reminder", title="Hi", body="Body"
    )

    row = (
        await db_session.execute(select(NotificationLog).where(NotificationLog.user_id == user.id))
    ).scalar_one()
    assert row.status == "sent"
    assert row.channel_ids == ["chan1"]

    assert len(_FakeApprise.instances) == 1
    assert _FakeApprise.instances[0].targets == {"chan1": SECRET_URL}


# Case 41: Apprise URLs never appear in captured logs.


async def test_apprise_urls_never_appear_in_logs(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notifier_module.apprise, "Apprise", _FakeApprise)
    user = await make_user(db_session, email="notif-logsafe@example.com")
    _configure(session_maker, {"notes.reminder": object()})

    store = notifier_module._context.store  # type: ignore[union-attr]
    await store.set(
        db_session,
        user_id=user.id,
        domain="core",
        key="notifier.channels",
        value=[{"id": "chan1", "label": "Chan 1", "enabled": True}],
    )
    await store.set(
        db_session,
        user_id=user.id,
        domain="core",
        key="notifier.urls",
        value={"chan1": SECRET_URL},
        is_secret=True,
    )
    await db_session.commit()

    with structlog.testing.capture_logs() as captured:
        await notifier_module._deliver_notification(
            user_id=str(user.id), notification_type="notes.reminder", title="Hi", body="Body"
        )

    rendered = repr(captured)
    assert SECRET_URL not in rendered
