"""core.translation_call table (M22)

Revision ID: 0004_core_translation_call
Revises: 0003_core_llm_call
Create Date: 2026-08-14

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_core_translation_call"
down_revision: str | None = "0003_core_llm_call"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE core.translation_call (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID        NULL,
            backend      TEXT        NOT NULL,
            operation    TEXT        NOT NULL,
            source_lang  TEXT        NULL,
            target_lang  TEXT        NULL,
            text_count   INTEGER     NOT NULL DEFAULT 0,
            char_count   INTEGER     NOT NULL DEFAULT 0,
            latency_ms   INTEGER     NOT NULL DEFAULT 0,
            outcome      TEXT        NOT NULL,
            error_code   TEXT        NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_translation_call_outcome CHECK (outcome IN
                ('ok','not_supported','unavailable','quota_exceeded','rejected','too_large','invalid_response'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_core_translation_call_created
            ON core.translation_call (created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_core_translation_call_backend_created
            ON core.translation_call (backend, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS core.translation_call")
