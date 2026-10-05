"""learning: source.asset_id -> file_id (M18 v2)

Revision ID: 0002_learning_source_file
Revises: 0001_learning_initial
Create Date: 2026-10-04

M18 v2 replaced core.assets with core.files and started with an empty table
(docs/milestones/server/M18-files.md §14), so every existing pointer would
dangle: the column is renamed AND nulled. raw_text is untouched, so existing
sources keep working; they only lose the original upload.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_learning_source_file"
down_revision: str | None = "0001_learning_initial"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE learning.source RENAME COLUMN asset_id TO file_id")
    op.execute("UPDATE learning.source SET file_id = NULL WHERE file_id IS NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE learning.source RENAME COLUMN file_id TO asset_id")
