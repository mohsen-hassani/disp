from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PlantCreated:
    plant_id: UUID
    user_id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class PlantDeleted:
    plant_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True)
class CareCompleted:
    plant_id: UUID
    interval_id: UUID
    user_id: UUID
    action_name: str
    completed_on: date
    days_late: int
