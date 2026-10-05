"""core.llm_call table (M19)

Revision ID: 0003_core_llm_call
Revises: 0002_core_assets
Create Date: 2026-08-10

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_core_llm_call"
down_revision: str | None = "0002_core_assets"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE core.llm_call (
            id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id            UUID        NULL,
            call_name          TEXT        NOT NULL,
            model              TEXT        NOT NULL,
            input_tokens       INTEGER     NOT NULL DEFAULT 0,
            cached_read_tokens INTEGER     NOT NULL DEFAULT 0,
            output_tokens      INTEGER     NOT NULL DEFAULT 0,
            latency_ms         INTEGER     NOT NULL DEFAULT 0,
            outcome            TEXT        NOT NULL,
            error_code         TEXT        NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_llm_call_outcome CHECK (outcome IN
                ('ok','refused','truncated','invalid_output','unavailable','too_large'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_core_llm_call_created
            ON core.llm_call (created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_core_llm_call_name_created
            ON core.llm_call (call_name, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS core.llm_call")
