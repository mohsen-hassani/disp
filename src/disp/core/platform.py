from dataclasses import dataclass
from typing import TYPE_CHECKING

from disp.core.config import Settings
from disp.core.events import EventBus
from disp.core.notifier import NotifierFacade
from disp.core.scheduler import SchedulerFacade
from disp.core.settings_store import SettingsStore

if TYPE_CHECKING:
    from disp.core.files import FileStore
    from disp.core.llm import LLMFacade
    from disp.core.registry import Registry
    from disp.core.translation import TranslationFacade


@dataclass
class Platform:
    settings: Settings
    events: EventBus
    scheduler: SchedulerFacade  # .task(name), .defer(name, **kwargs)
    notifier: NotifierFacade  # .send(...)
    store: SettingsStore
    files: "FileStore"
    llm: "LLMFacade"  # .generate(), .generate_text(), .embed(), .usage() — see disp.core.llm
    # .translate(), .detect() and their _sync twins — see disp.core.translation
    translation: "TranslationFacade"
    registry: "Registry"  # read-only accessors only
