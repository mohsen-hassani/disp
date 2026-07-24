import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from disp.core.db import Base

SCHEMA = "notes"


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(
            "char_length(body) BETWEEN 1 AND 20000",
            name="ck_notes_body_len",
        ),
        CheckConstraint(
            "title IS NULL OR char_length(title) BETWEEN 1 AND 200",
            name="ck_notes_title_len",
        ),
        Index(
            "ix_notes_user_created",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_notes_user_pinned",
            "user_id",
            "pinned",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_notes_search",
            text("to_tsvector('simple', coalesce(title,'') || ' ' || body)"),
            postgresql_using="gin",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # No FK to core.users: modules must not create cross-schema foreign keys (§6.1).
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    pinned: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["Note"]
