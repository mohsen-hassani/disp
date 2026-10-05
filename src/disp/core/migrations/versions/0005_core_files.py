"""core.files table — M18 v2 (S3/R2-only file service)

Drops v1's core.assets (local-disk era) and creates core.files. No data is
carried over: M18 v2 started fresh by decision (docs/milestones/server/
M18-files.md §14). The plants and learning branches null their own pointers
in their matching revisions.

Revision ID: 0005_core_files
Revises: 0004_core_translation_call
Create Date: 2026-10-04

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_core_files"
down_revision: str | None = "0004_core_translation_call"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS core.assets")
    op.execute(
        """
        CREATE TABLE core.files (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id     UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
            domain            TEXT        NOT NULL,
            purpose           TEXT        NOT NULL,
            name              TEXT        NOT NULL,
            content_type      TEXT        NOT NULL,
            byte_size         BIGINT      NOT NULL,
            sha256            TEXT        NOT NULL,
            backend           TEXT        NOT NULL,
            bucket            TEXT        NOT NULL,
            storage_key       TEXT        NOT NULL,
            link_ttl_seconds  INTEGER     NOT NULL,
            attributes        JSONB       NOT NULL DEFAULT '{}'::jsonb,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at        TIMESTAMPTZ NULL,
            CONSTRAINT ck_files_domain    CHECK (domain ~ '^[a-z][a-z0-9_]{1,31}$'),
            CONSTRAINT ck_files_purpose   CHECK (purpose ~ '^[a-z][a-z0-9_]{1,63}$'),
            CONSTRAINT ck_files_name      CHECK (length(name) BETWEEN 1 AND 255),
            CONSTRAINT ck_files_byte_size CHECK (byte_size > 0),
            CONSTRAINT ck_files_sha256    CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_files_link_ttl  CHECK (link_ttl_seconds BETWEEN 60 AND 604800)
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX uq_files_location ON core.files (backend, bucket, storage_key)")
    op.execute(
        """
        CREATE INDEX ix_files_owner
            ON core.files (owner_user_id, created_at DESC)
            WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_files_lookup
            ON core.files (domain, purpose)
            WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_files_purge
            ON core.files (deleted_at)
            WHERE deleted_at IS NOT NULL
        """
    )


def downgrade() -> None:
    # Restores v1's (empty) schema; objects written under v2 stay in the
    # bucket and are not v1's concern.
    op.execute("DROP TABLE IF EXISTS core.files")
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
        "CREATE UNIQUE INDEX uq_assets_backend_storage_key ON core.assets (backend, storage_key)"
    )
    op.execute(
        """
        CREATE INDEX ix_assets_owner ON core.assets (owner_user_id, created_at DESC)
            WHERE deleted_at IS NULL
        """
    )
    op.execute(
        "CREATE INDEX ix_assets_lookup ON core.assets (domain, purpose) WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_assets_sweep ON core.assets (deleted_at) WHERE deleted_at IS NOT NULL"
    )
