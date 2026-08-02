from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# What a calendar cell entry represents:
#   done      - a CareLog row; something actually completed on that day
#   overdue   - an active interval whose next_due_on has already passed
#   due       - an active interval falling due today or later
#   projected - a future repeat derived from next_due_on + n * interval_days,
#               shown greyed out because completing early or late moves it
CalendarKind = Literal["done", "overdue", "due", "projected"]


class PlantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    care_notes: str | None = Field(default=None, max_length=20000)


class PlantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    care_notes: str | None = Field(default=None, max_length=20000)


class CareIntervalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    interval_days: int = Field(ge=1, le=3650)
    # "I last watered it on ..." — the first due date is this plus
    # interval_days. Defaults to today, so a bare create means "due in
    # interval_days from now".
    last_done_on: date | None = None


class CareIntervalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    interval_days: int | None = Field(default=None, ge=1, le=3650)
    next_due_on: date | None = None
    active: bool | None = None


class CareIntervalOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    plant_id: UUID
    name: str
    interval_days: int
    next_due_on: date
    last_done_on: date | None
    active: bool
    # Derived against the caller's "today": 0 means due today, negative means
    # not due yet, positive means this many days behind.
    days_overdue: int
    created_at: datetime
    updated_at: datetime


class PlantOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    description: str | None
    care_notes: str | None
    has_image: bool
    image_url: str | None
    # Rollups across this plant's active intervals, so a list view can badge
    # a plant without a second round trip per row.
    due_count: int
    max_days_overdue: int
    next_due_on: date | None
    created_at: datetime
    updated_at: datetime


class PlantDetailOut(PlantOut):
    intervals: list[CareIntervalOut]


class CompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Defaults to today. Back-dating is allowed (up to a year) so "I actually
    # watered it on Saturday" schedules the next one correctly; future dates
    # are rejected in the service layer.
    completed_on: date | None = None
    note: str | None = Field(default=None, max_length=2000)


class CareLogOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    plant_id: UUID
    interval_id: UUID | None
    action_name: str
    due_on: date
    completed_on: date
    days_late: int
    note: str | None
    created_at: datetime


class CompleteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    log: CareLogOut
    interval: CareIntervalOut


class DueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plant_id: UUID
    plant_name: str
    interval_id: UUID
    action_name: str
    due_on: date
    days_overdue: int


class DueSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date
    count: int
    overdue_count: int
    max_days_overdue: int
    summary: str
    items: list[DueItem]


class CalendarEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date
    kind: CalendarKind
    plant_id: UUID
    plant_name: str
    interval_id: UUID | None
    action_name: str
    log_id: UUID | None = None
    days_late: int | None = None


class CalendarOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: str
    start: date
    end: date
    entries: list[CalendarEntry]
