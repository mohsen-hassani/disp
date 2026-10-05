"""plants: image_asset_id -> image_file_id (M18 v2)

Revision ID: 0003_plants_image_file
Revises: 0002_plants_image_asset
Create Date: 2026-10-04

M18 v2 replaced core.assets with core.files and started with an empty table
(docs/milestones/server/M18-files.md §14), so every existing pointer would
dangle: the column is renamed AND nulled.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_plants_image_file"
down_revision: str | None = "0002_plants_image_asset"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE plants.plant RENAME COLUMN image_asset_id TO image_file_id")
    op.execute("UPDATE plants.plant SET image_file_id = NULL WHERE image_file_id IS NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE plants.plant RENAME COLUMN image_file_id TO image_asset_id")
