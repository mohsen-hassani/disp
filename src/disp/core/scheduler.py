import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeVar
from zoneinfo import ZoneInfo

import procrastinate
import structlog
from procrastinate import PsycopgConnector, RetryStrategy

from disp.core.config import get_settings
from disp.core.contract import KEY_RE

if TYPE_CHECKING:
    from disp.core.registry import Registry

logger = structlog.get_logger(__name__)

_KEY_PATTERN = re.compile(KEY_RE)
_DIALECT_SUFFIX_RE = re.compile(r"^postgresql\+[a-z0-9_]+://")

F = TypeVar("F", bound=Callable[..., Any])


def to_psycopg_dsn(sqlalchemy_url: str) -> str:
    """Strip the SQLAlchemy `+driver` marker; psycopg wants a bare postgresql:// DSN."""
    return _DIALECT_SUFFIX_RE.sub("postgresql://", sqlalchemy_url, count=1)


def default_retry_strategy(max_attempts: int) -> RetryStrategy:
    return RetryStrategy(max_attempts=max_attempts, wait=10, linear_wait=0)


app = procrastinate.App(
    connector=PsycopgConnector(conninfo=to_psycopg_dsn(get_settings().database_url_sync))
)


class SchedulerRegistrationError(Exception):
    pass


class SchedulerFacade:
    """Thin wrapper so modules never import Procrastinate directly (§13.2)."""

    def __init__(self, procrastinate_app: procrastinate.App) -> None:
        self._app = procrastinate_app

    def task(self, name: str, *, queue: str = "default", retry: int = 3) -> Callable[[F], F]:
        if not _KEY_PATTERN.match(name):
            raise ValueError(f"scheduler task name {name!r} must match {KEY_RE!r}")
        if name in self._app.tasks:
            raise SchedulerRegistrationError(f"duplicate scheduler task name: {name!r}")
        decorator = self._app.task(name=name, queue=queue, retry=default_retry_strategy(retry))
        return decorator  # type: ignore[return-value]

    async def defer(self, name: str, **kwargs: Any) -> None:
        task = self._app.tasks.get(name)
        if task is None:
            raise ValueError(f"unknown scheduler task: {name!r}")
        await task.defer_async(**kwargs)

    def register_periodic(self, name: str, cron: str) -> None:
        """Used by Registry.wire() to bind a ScheduledJobSpec's cron (§9.2 step 3)."""
        task = self._app.tasks.get(name)
        if task is None:
            raise SchedulerRegistrationError(f"cannot schedule unknown task: {name!r}")
        self._app.periodic_registry.register_task(
            task=task, cron=cron, periodic_id="", configure_kwargs={}
        )


_active_registry: "Registry | None" = None


def set_registry(registry: "Registry") -> None:
    global _active_registry
    _active_registry = registry


@app.periodic(cron=get_settings().daily_planner_cron)
@app.task(name="core.daily_planner", retry=default_retry_strategy(3))
async def daily_planner(timestamp: int) -> None:
    settings = get_settings()
    now = datetime.fromtimestamp(timestamp, tz=UTC).astimezone(ZoneInfo(settings.timezone))
    local_date = now.date().isoformat()
    logger.info("daily_planner_started", date=local_date)

    job_names = [job.name for job in _active_registry.scheduled_jobs] if _active_registry else []
    for name in job_names:
        logger.info("daily_planner_job", name=name)

    logger.info("daily_planner_completed", date=local_date, count=len(job_names))
