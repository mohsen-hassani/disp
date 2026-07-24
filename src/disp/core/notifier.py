from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

import apprise
import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.contract import SettingsPanelSpec
from disp.core.db import session_scope
from disp.core.models import NotificationLog
from disp.core.scheduler import SchedulerFacade, app, default_retry_strategy
from disp.core.settings_store import SettingsStore

if TYPE_CHECKING:
    from disp.core.registry import Registry

logger = structlog.get_logger(__name__)

DIAGNOSTIC_MAX_LEN = 1000
CHANNEL_ID_RE = r"^[a-z][a-z0-9_-]{0,31}$"


class NotifierDeliveryError(Exception):
    pass


class ChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=CHANNEL_ID_RE)
    label: str
    enabled: bool = True


class NotifierSettingsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channels: list[ChannelConfig] = Field(default_factory=list)
    routing: dict[str, list[str]] = Field(default_factory=dict)
    # Write-only: never returned in plaintext by any API (§14.1, §14.3).
    urls: dict[str, str] = Field(default_factory=dict, json_schema_extra={"secret": True})


NOTIFIER_SETTINGS_PANEL = SettingsPanelSpec(
    key="core.notifier",
    title="Notifications",
    description="Configure notification channels and routing.",
    schema_model=NotifierSettingsSchema,
    scope="user",
)


@dataclass
class _NotifierContext:
    store: SettingsStore
    session_maker: async_sessionmaker[AsyncSession]
    registry: "Registry"


_context: _NotifierContext | None = None


def configure(
    *,
    store: SettingsStore,
    session_maker: async_sessionmaker[AsyncSession],
    registry: "Registry",
) -> None:
    """Called once during platform construction so the deferred delivery task
    (which cannot receive dependency-injected arguments) has what it needs."""
    global _context
    _context = _NotifierContext(store=store, session_maker=session_maker, registry=registry)


class NotifierFacade:
    def __init__(self, scheduler: SchedulerFacade) -> None:
        self._scheduler = scheduler

    async def send(
        self,
        user_id: UUID,
        notification_type: str,
        title: str,
        body: str,
        url: str | None = None,
    ) -> None:
        if _context is None or notification_type not in _context.registry.notification_types:
            raise ValueError(f"unknown notification type: {notification_type!r}")
        await self._scheduler.defer(
            "core.deliver_notification",
            user_id=str(user_id),
            notification_type=notification_type,
            title=title,
            body=body,
            url=url,
        )


async def _write_log(
    session: AsyncSession,
    *,
    user_id: UUID,
    notification_type: str,
    title: str,
    body: str,
    channel_ids: list[str],
    status: str,
    error: str | None,
) -> None:
    session.add(
        NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            body=body,
            channel_ids=channel_ids,
            status=status,
            error=error[:DIAGNOSTIC_MAX_LEN] if error else None,
        )
    )


@app.task(name="core.deliver_notification", retry=default_retry_strategy(3))
async def _deliver_notification(
    user_id: str,
    notification_type: str,
    title: str,
    body: str,
    url: str | None = None,
) -> None:
    if _context is None:
        raise RuntimeError("disp.core.notifier.configure() was not called before startup")

    effective_body = f"{body}\n{url}" if url else body
    should_raise = False
    raise_message = ""

    async with session_scope(_context.session_maker) as session:
        target_user_id = UUID(user_id)

        routing = await _context.store.get(
            session, user_id=target_user_id, domain="core", key="notifier.routing", default={}
        )
        channel_ids = routing.get(notification_type) if isinstance(routing, dict) else None

        if channel_ids is None:
            channels = await _context.store.get(
                session, user_id=target_user_id, domain="core", key="notifier.channels", default=[]
            )
            channel_ids = [c["id"] for c in channels if c.get("enabled")]

        if not channel_ids:
            await _write_log(
                session,
                user_id=target_user_id,
                notification_type=notification_type,
                title=title,
                body=body,
                channel_ids=[],
                status="no_channels",
                error=None,
            )
            logger.info(
                "notification_delivered",
                notification_type=notification_type,
                channel_ids=[],
                status="no_channels",
            )
            return

        urls_map = (
            await _context.store.get(
                session, user_id=target_user_id, domain="core", key="notifier.urls", default={}
            )
            or {}
        )
        targets = {cid: urls_map[cid] for cid in channel_ids if cid in urls_map}

        if not targets:
            error = "No configured Apprise URL for the selected channels."
            await _write_log(
                session,
                user_id=target_user_id,
                notification_type=notification_type,
                title=title,
                body=body,
                channel_ids=channel_ids,
                status="failed",
                error=error,
            )
            should_raise = True
            raise_message = error
        else:
            apprise_obj = apprise.Apprise()
            for channel_id, apprise_url in targets.items():
                apprise_obj.add(apprise_url, tag=channel_id)

            results: dict[str, bool] = {}
            for channel_id in targets:
                try:
                    ok = await apprise_obj.async_notify(
                        title=title, body=effective_body, tag=channel_id
                    )
                except Exception:  # Apprise plugin failures must not crash the task
                    ok = False
                results[channel_id] = bool(ok)

            if all(results.values()):
                status = "sent"
                error = None
            elif any(results.values()):
                failed = [cid for cid, ok in results.items() if not ok]
                status = "partial"
                error = f"Delivery failed for channels: {', '.join(failed)}"
            else:
                status = "failed"
                error = "Delivery failed for all channels."

            await _write_log(
                session,
                user_id=target_user_id,
                notification_type=notification_type,
                title=title,
                body=body,
                channel_ids=list(targets.keys()),
                status=status,
                error=error,
            )
            logger.info(
                "notification_delivered",
                notification_type=notification_type,
                channel_ids=list(targets.keys()),
                status=status,
            )
            if status == "failed":
                should_raise = True
                raise_message = error or "notification delivery failed"

    # The log write above is committed (session_scope exited normally) before
    # we raise here, so a retry never loses the notification_log record.
    if should_raise:
        raise NotifierDeliveryError(raise_message)
