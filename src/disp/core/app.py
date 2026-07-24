import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from disp import __version__
from disp.core import dashboard as dashboard_module
from disp.core import health as health_module
from disp.core import settings_store as settings_store_module
from disp.core.auth import routes as auth_routes
from disp.core.config import get_settings
from disp.core.contract import ScheduledJobSpec
from disp.core.db import create_engine, create_session_maker
from disp.core.errors import limiter, register_exception_handlers
from disp.core.events import EventBus, set_event_bus
from disp.core.logging import RequestIdMiddleware, configure_logging
from disp.core.notifier import NOTIFIER_SETTINGS_PANEL, NotifierFacade
from disp.core.notifier import configure as configure_notifier
from disp.core.platform import Platform
from disp.core.registry import Registry
from disp.core.scheduler import SchedulerFacade, set_registry
from disp.core.scheduler import app as procrastinate_app
from disp.core.settings_store import SettingsStore

logger = structlog.get_logger(__name__)

DATABASE_STARTUP_RETRIES = 5
DATABASE_STARTUP_BACKOFF_SECONDS = 2


async def _wait_for_database(engine: AsyncEngine) -> None:
    last_exc: Exception | None = None
    for attempt in range(1, DATABASE_STARTUP_RETRIES + 1):
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return
        except (SQLAlchemyError, OSError) as exc:
            last_exc = exc
            logger.warning(
                "database_unreachable_retrying",
                attempt=attempt,
                max_attempts=DATABASE_STARTUP_RETRIES,
            )
            if attempt < DATABASE_STARTUP_RETRIES:
                await asyncio.sleep(DATABASE_STARTUP_BACKOFF_SECONDS)

    logger.critical("database_unreachable", exc_info=last_exc)
    raise RuntimeError(
        f"database is unreachable after {DATABASE_STARTUP_RETRIES} retries"
    ) from last_exc


def create_app() -> FastAPI:
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

    limiter.enabled = settings.rate_limit_enabled

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await _wait_for_database(engine)
        await procrastinate_app.open_async()
        try:
            yield
        finally:
            await procrastinate_app.close_async()
            await engine.dispose()

    app = FastAPI(
        title="MyStuff",
        version=__version__,
        openapi_url="/openapi.json",
        docs_url="/docs" if settings.env != "production" else None,
        redoc_url="/redoc" if settings.env != "production" else None,
        redirect_slashes=False,
        lifespan=lifespan,
    )

    app.state.registry = registry
    app.state.platform = platform
    app.state.session_maker = session_maker
    app.state.engine = engine
    app.state.limiter = limiter

    # Middleware order is outermost-first: RequestIdMiddleware, CORSMiddleware,
    # SlowAPIMiddleware (§9.3 step 5). Starlette makes the LAST-added middleware
    # the outermost, so they are added here in the reverse order.
    app.add_middleware(SlowAPIMiddleware)
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
        )
    app.add_middleware(RequestIdMiddleware)

    register_exception_handlers(app)

    app.include_router(health_module.router, prefix="/health")
    app.include_router(auth_routes.router, prefix="/api/auth")
    app.include_router(dashboard_module.router, prefix="/api/dashboard")
    app.include_router(settings_store_module.router, prefix="/api/settings")

    registry.discover()
    registry.wire(app, platform)

    registry.register_core_scheduled_job(
        ScheduledJobSpec(
            name="core.daily_planner",
            cron=settings.daily_planner_cron,
            description="Proves the scheduler mechanism; logs registered scheduled jobs.",
        )
    )
    registry.register_core_settings_panel(NOTIFIER_SETTINGS_PANEL)

    return app
