"""core schema initial

Revision ID: 0001_core_initial
Revises:
Create Date: 2026-07-24

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_core_initial"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE SCHEMA IF NOT EXISTS core")

    op.execute(
        """
        CREATE TABLE core.users (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            email             TEXT        NOT NULL,
            display_name      TEXT        NOT NULL,
            password_hash     TEXT        NULL,
            is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
            is_admin          BOOLEAN     NOT NULL DEFAULT FALSE,
            external_issuer   TEXT        NULL,
            external_subject  TEXT        NULL,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_users_display_name_len CHECK (char_length(display_name) BETWEEN 1 AND 100),
            CONSTRAINT ck_users_external_pair CHECK (
                (external_issuer IS NULL) = (external_subject IS NULL)
            ),
            CONSTRAINT ck_users_has_credential CHECK (
                password_hash IS NOT NULL OR external_subject IS NOT NULL
            )
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX uq_users_email_lower ON core.users (lower(email))")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_users_external
            ON core.users (external_issuer, external_subject)
            WHERE external_subject IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE TABLE core.invites (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            email            TEXT        NOT NULL,
            token_hash       TEXT        NOT NULL UNIQUE,
            is_admin         BOOLEAN     NOT NULL DEFAULT FALSE,
            created_by       UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
            expires_at       TIMESTAMPTZ NOT NULL,
            accepted_at      TIMESTAMPTZ NULL,
            accepted_user_id UUID        NULL REFERENCES core.users(id) ON DELETE SET NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_invites_email_lower ON core.invites (lower(email))")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_invites_pending_email
            ON core.invites (lower(email))
            WHERE accepted_at IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE core.sessions (
            id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
            family_id           UUID        NOT NULL,
            refresh_token_hash  TEXT        NOT NULL UNIQUE,
            previous_session_id UUID        NULL REFERENCES core.sessions(id) ON DELETE SET NULL,
            device_label        TEXT        NULL,
            user_agent          TEXT        NULL,
            ip_address          TEXT        NULL,
            issued_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at          TIMESTAMPTZ NOT NULL,
            rotated_at          TIMESTAMPTZ NULL,
            revoked_at          TIMESTAMPTZ NULL,
            revoked_reason      TEXT        NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_sessions_revoked_reason CHECK (
                revoked_reason IS NULL OR revoked_reason IN
                ('logout','rotation','reuse_detected','password_change','admin','expired')
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_sessions_user_id  ON core.sessions (user_id)")
    op.execute("CREATE INDEX ix_sessions_family_id ON core.sessions (family_id)")

    op.execute(
        """
        CREATE TABLE core.api_tokens (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
            name         TEXT        NOT NULL,
            token_hash   TEXT        NOT NULL UNIQUE,
            token_prefix TEXT        NOT NULL,
            last_used_at TIMESTAMPTZ NULL,
            expires_at   TIMESTAMPTZ NULL,
            revoked_at   TIMESTAMPTZ NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_api_tokens_name_len CHECK (char_length(name) BETWEEN 1 AND 64)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_api_tokens_user_name
            ON core.api_tokens (user_id, name) WHERE revoked_at IS NULL
        """
    )
    op.execute("CREATE INDEX ix_api_tokens_user_id ON core.api_tokens (user_id)")

    op.execute(
        """
        CREATE TABLE core.acl (
            id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            resource_type TEXT        NOT NULL,
            resource_id   TEXT        NOT NULL,
            user_id       UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
            permission    TEXT        NOT NULL,
            granted_by    UUID        NULL REFERENCES core.users(id) ON DELETE SET NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_acl_permission CHECK (permission IN ('read','write','owner'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_acl_resource_user
            ON core.acl (resource_type, resource_id, user_id)
        """
    )
    op.execute("CREATE INDEX ix_acl_user_lookup ON core.acl (user_id, resource_type)")

    op.execute(
        """
        CREATE TABLE core.settings (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID        NULL REFERENCES core.users(id) ON DELETE CASCADE,
            module_domain   TEXT        NOT NULL,
            key             TEXT        NOT NULL,
            value_json      JSONB       NULL,
            value_encrypted BYTEA       NULL,
            is_secret       BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_settings_one_value CHECK (
                (value_json IS NULL) <> (value_encrypted IS NULL)
            ),
            CONSTRAINT ck_settings_secret_storage CHECK (
                (is_secret = TRUE  AND value_encrypted IS NOT NULL) OR
                (is_secret = FALSE AND value_json      IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_settings_scope
            ON core.settings (user_id, module_domain, key) NULLS NOT DISTINCT
        """
    )

    op.execute(
        """
        CREATE TABLE core.notification_log (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id           UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
            notification_type TEXT        NOT NULL,
            title             TEXT        NOT NULL,
            body              TEXT        NOT NULL,
            channel_ids       TEXT[]      NOT NULL DEFAULT '{}',
            status            TEXT        NOT NULL,
            error             TEXT        NULL,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_notification_log_status CHECK (
                status IN ('sent','partial','failed','no_channels')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_notification_log_user_created
            ON core.notification_log (user_id, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS core.notification_log")
    op.execute("DROP TABLE IF EXISTS core.settings")
    op.execute("DROP TABLE IF EXISTS core.acl")
    op.execute("DROP TABLE IF EXISTS core.api_tokens")
    op.execute("DROP TABLE IF EXISTS core.sessions")
    op.execute("DROP TABLE IF EXISTS core.invites")
    op.execute("DROP TABLE IF EXISTS core.users")
