from dataclasses import dataclass
from typing import TYPE_CHECKING

from disp.core.config import Settings
from disp.core.events import EventBus
from disp.core.notifier import NotifierFacade
from disp.core.scheduler import SchedulerFacade
from disp.core.settings_store import SettingsStore

if TYPE_CHECKING:
    from disp.core.registry import Registry


@dataclass
class Platform:
    settings: Settings
    events: EventBus
    scheduler: SchedulerFacade  # .task(name), .defer(name, **kwargs)
    notifier: NotifierFacade  # .send(...)
    store: SettingsStore
    registry: "Registry"  # read-only accessors only
