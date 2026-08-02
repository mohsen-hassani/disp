import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from disp.core.db import Base

SCHEMA = "plants"


class Plant(Base):
    """A single plant the user is looking after.

    `care_notes` is the free-text "how to look after this one" prose; the
    machine-readable recurring actions live in `CareInterval` instead.
    """

    __tablename__ = "plant"
    __table_args__ = (
        CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="ck_plants_name_len"),
        CheckConstraint(
            "description IS NULL OR char_length(description) <= 2000",
            name="ck_plants_description_len",
        ),
        CheckConstraint(
            "care_notes IS NULL OR char_length(care_notes) <= 20000",
            name="ck_plants_care_notes_len",
        ),
        Index(
            "ix_plants_plant_user_created",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # No FK to core.users: modules must not create cross-schema foreign keys (§6.1).
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    care_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Path relative to the module's media root, never an absolute path: the
    # volume mount point differs between the container and a local `uv run`.
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CareInterval(Base):
    """A recurring action for one plant ("Water", every 15 days).

    `next_due_on` is stored rather than derived from `last_done_on +
    interval_days` so that completing late reschedules from the completion
    date (done on the 3rd for a 15-day interval -> next due the 18th), and so
    a user can hand-correct a single occurrence without rewriting history.
    """

    __tablename__ = "care_interval"
    __table_args__ = (
        CheckConstraint("char_length(name) BETWEEN 1 AND 80", name="ck_plants_interval_name_len"),
        CheckConstraint("interval_days BETWEEN 1 AND 3650", name="ck_plants_interval_days_range"),
        Index("ix_plants_interval_plant", "plant_id"),
        Index(
            "ix_plants_interval_due",
            "next_due_on",
            postgresql_where=text("active"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.plant.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    next_due_on: Mapped[date] = mapped_column(Date, nullable=False)
    last_done_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CareLog(Base):
    """An append-only record of one completed action.

    `interval_id` is ON DELETE SET NULL and `action_name` is a snapshot taken
    at completion time, so deleting or renaming an interval never rewrites or
    erases what the calendar shows for past months.
    """

    __tablename__ = "care_log"
    __table_args__ = (
        CheckConstraint(
            "char_length(action_name) BETWEEN 1 AND 80", name="ck_plants_log_action_name_len"
        ),
        CheckConstraint("note IS NULL OR char_length(note) <= 2000", name="ck_plants_log_note_len"),
        Index("ix_plants_log_plant_completed", "plant_id", text("completed_on DESC")),
        Index("ix_plants_log_user_completed", "user_id", text("completed_on DESC")),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.plant.id", ondelete="CASCADE"),
        nullable=False,
    )
    interval_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.care_interval.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action_name: Mapped[str] = mapped_column(Text, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    completed_on: Mapped[date] = mapped_column(Date, nullable=False)
    # completed_on - due_on; negative when the action was done early.
    days_late: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["CareInterval", "CareLog", "Plant"]
