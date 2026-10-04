import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from disp.core.db import Base

SCHEMA = "core"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 100",
            name="ck_users_display_name_len",
        ),
        CheckConstraint(
            "(external_issuer IS NULL) = (external_subject IS NULL)",
            name="ck_users_external_pair",
        ),
        CheckConstraint(
            "password_hash IS NOT NULL OR external_subject IS NOT NULL",
            name="ck_users_has_credential",
        ),
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
        Index(
            "uq_users_external",
            "external_issuer",
            "external_subject",
            unique=True,
            postgresql_where=text("external_subject IS NOT NULL"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    is_admin: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    external_issuer: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (
        Index("ix_invites_email_lower", text("lower(email)")),
        Index(
            "uq_invites_pending_email",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("accepted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    is_admin: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "revoked_reason IS NULL OR revoked_reason IN "
            "('logout','rotation','reuse_detected','password_change','admin','expired')",
            name="ck_sessions_revoked_reason",
        ),
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_family_id", "family_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    previous_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    device_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = (
        CheckConstraint(
            "char_length(name) BETWEEN 1 AND 64",
            name="ck_api_tokens_name_len",
        ),
        Index(
            "uq_api_tokens_user_name",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_api_tokens_user_id", "user_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    token_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Acl(Base):
    __tablename__ = "acl"
    __table_args__ = (
        CheckConstraint(
            "permission IN ('read','write','owner')",
            name="ck_acl_permission",
        ),
        Index(
            "uq_acl_resource_user",
            "resource_type",
            "resource_id",
            "user_id",
            unique=True,
        ),
        Index("ix_acl_user_lookup", "user_id", "resource_type"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    permission: Mapped[str] = mapped_column(Text, nullable=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Setting(Base):
    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint(
            "(value_json IS NULL) <> (value_encrypted IS NULL)",
            name="ck_settings_one_value",
        ),
        CheckConstraint(
            "(is_secret = TRUE  AND value_encrypted IS NOT NULL) OR "
            "(is_secret = FALSE AND value_json      IS NOT NULL)",
            name="ck_settings_secret_storage",
        ),
        Index(
            "uq_settings_scope",
            "user_id",
            "module_domain",
            "key",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=True,
    )
    module_domain: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    # none_as_null=True: a Python None must bind as SQL NULL, not the JSON
    # scalar "null" (which is a non-NULL JSONB value and would violate
    # ck_settings_one_value whenever this column is meant to be unset).
    value_json: Mapped[dict[str, object] | list[object] | str | int | float | bool | None] = (
        mapped_column(JSONB(none_as_null=True), nullable=True)
    )
    value_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_secret: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NotificationLog(Base):
    __tablename__ = "notification_log"
    __table_args__ = (
        CheckConstraint(
            "status IN ('sent','partial','failed','no_channels')",
            name="ck_notification_log_status",
        ),
        Index("ix_notification_log_user_created", "user_id", text("created_at DESC")),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    notification_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    channel_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Asset(Base):
    """M18: core file/asset service. Assets are immutable — there is no update,
    only soft-delete (`deleted_at`) followed by the sweeper reaping the object
    and the row once past the grace period. See src/disp/core/files/ and
    docs/milestones/server/M18-files.md §4.
    """

    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "domain ~ '^[a-z][a-z0-9_]{1,31}$'",
            name="ck_assets_domain",
        ),
        CheckConstraint(
            "purpose ~ '^[a-z][a-z0-9_]{1,63}$'",
            name="ck_assets_purpose",
        ),
        CheckConstraint(
            "byte_size > 0",
            name="ck_assets_byte_size",
        ),
        CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_assets_sha256",
        ),
        Index(
            "uq_assets_backend_storage_key",
            "backend",
            "storage_key",
            unique=True,
        ),
        Index(
            "ix_assets_owner",
            "owner_user_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_assets_lookup",
            "domain",
            "purpose",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_assets_sweep",
            "deleted_at",
            postgresql_where=text("deleted_at IS NOT NULL"),
        ),
        {"schema": SCHEMA},
    )

    # Both a Python-side default and a server_default, unlike every other
    # table here: §5 requires the id be known *before* the row is even
    # constructed, because it's baked into the storage key the backend writes
    # bytes to first (I1). server_default stays for hand-written SQL.
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    backend: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    # none_as_null=False, unlike Setting.value_json (:255-260): attributes is
    # NOT NULL with a '{}' default and never needs to represent SQL NULL.
    attributes: Mapped[dict[str, object]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = [
    "SCHEMA",
    "Acl",
    "ApiToken",
    "Asset",
    "Invite",
    "NotificationLog",
    "Session",
    "Setting",
    "User",
]
