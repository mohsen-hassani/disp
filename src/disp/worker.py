import asyncio

import structlog
from cryptography.fernet import Fernet

from disp.core.config import get_settings
from disp.core.contract import ScheduledJobSpec
from disp.core.db import create_engine, create_session_maker
from disp.core.events import EventBus, set_event_bus
from disp.core.logging import configure_logging
from disp.core.notifier import NOTIFIER_SETTINGS_PANEL, NotifierFacade
from disp.core.notifier import configure as configure_notifier
from disp.core.platform import Platform
from disp.core.registry import Registry
from disp.core.scheduler import SchedulerFacade, set_registry
from disp.core.scheduler import app as procrastinate_app
from disp.core.settings_store import SettingsStore

logger = structlog.get_logger(__name__)


def _build_platform() -> Platform:
    """Performs steps 1-3 and 8 of §9.3 without constructing a FastAPI app,
    so module tasks and event subscriptions exist in the worker process too."""
    settings = get_settings()
    configure_logging(settings)

    engine = create_engine(settings.database_url)
    session_maker = create_session_maker(engine)

    event_bus = EventBus()
    set_event_bus(event_bus)

    fernet = Fernet(settings.settings_key.get_secret_value().encode("ascii"))
    store = SettingsStore(fernet)

    registry = Registry()
    set_registry(registry)

    scheduler_facade = SchedulerFacade(procrastinate_app)
    notifier_facade = NotifierFacade(scheduler_facade)
    configure_notifier(store=store, session_maker=session_maker, registry=registry)

    platform = Platform(
        settings=settings,
        events=event_bus,
        scheduler=scheduler_facade,
        notifier=notifier_facade,
        store=store,
        registry=registry,
    )

    registry.discover()
    registry.wire(None, platform)

    registry.register_core_scheduled_job(
        ScheduledJobSpec(
            name="core.daily_planner",
            cron=settings.daily_planner_cron,
            description="Proves the scheduler mechanism; logs registered scheduled jobs.",
        )
    )
    registry.register_core_settings_panel(NOTIFIER_SETTINGS_PANEL)

    return platform


async def _run() -> None:
    _build_platform()
    await procrastinate_app.open_async()
    try:
        await procrastinate_app.run_worker_async(
            concurrency=4,
            install_signal_handlers=True,
            listen_notify=True,
        )
    finally:
        await procrastinate_app.close_async()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
