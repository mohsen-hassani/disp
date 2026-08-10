"""core.assets table (M18)

Revision ID: 0002_core_assets
Revises: 0001_core_initial
Create Date: 2026-08-10

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_core_assets"
down_revision: str | None = "0001_core_initial"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE core.assets (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id     UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
            domain            TEXT        NOT NULL,
            purpose           TEXT        NOT NULL,
            content_type      TEXT        NOT NULL,
            byte_size         BIGINT      NOT NULL,
            sha256            TEXT        NOT NULL,
            original_filename TEXT        NULL,
            backend           TEXT        NOT NULL,
            storage_key       TEXT        NOT NULL,
            attributes        JSONB       NOT NULL DEFAULT '{}'::jsonb,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at        TIMESTAMPTZ NULL,
            CONSTRAINT ck_assets_domain     CHECK (domain ~ '^[a-z][a-z0-9_]{1,31}$'),
            CONSTRAINT ck_assets_purpose    CHECK (purpose ~ '^[a-z][a-z0-9_]{1,63}$'),
            CONSTRAINT ck_assets_byte_size  CHECK (byte_size > 0),
            CONSTRAINT ck_assets_sha256     CHECK (sha256 ~ '^[0-9a-f]{64}$')
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_assets_backend_storage_key
            ON core.assets (backend, storage_key)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_assets_owner
            ON core.assets (owner_user_id, created_at DESC)
            WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_assets_lookup
            ON core.assets (domain, purpose)
            WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_assets_sweep
            ON core.assets (deleted_at)
            WHERE deleted_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS core.assets")
