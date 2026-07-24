"""notes schema initial

Revision ID: 0001_notes_initial
Revises:
Create Date: 2026-07-24

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_notes_initial"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS notes")

    op.execute(
        """
        CREATE TABLE notes.notes (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID        NOT NULL,
            title      TEXT        NULL,
            body       TEXT        NOT NULL,
            pinned     BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ NULL,
            CONSTRAINT ck_notes_body_len  CHECK (char_length(body)  BETWEEN 1 AND 20000),
            CONSTRAINT ck_notes_title_len CHECK (title IS NULL OR char_length(title) BETWEEN 1 AND 200)
        )
        """
    )

    op.execute(
        """
        CREATE INDEX ix_notes_user_created
            ON notes.notes (user_id, created_at DESC) WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_notes_user_pinned
            ON notes.notes (user_id, pinned, created_at DESC) WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_notes_search
            ON notes.notes USING GIN (to_tsvector('simple', coalesce(title,'') || ' ' || body))
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notes.notes")
