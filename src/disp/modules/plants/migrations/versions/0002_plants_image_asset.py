"""plants: replace ad-hoc image columns with image_asset_id (M18)

Revision ID: 0002_plants_image_asset
Revises: 0001_plants_initial
Create Date: 2026-08-10

Operator note: before running this migration, run
`disp-admin files adopt --domain plants --purpose plant_photo --root <old media root>`
against the pre-upgrade media root. This migration DROPS image_path,
image_content_type and image_updated_at — any plant photo not already
adopted into core.assets is unrecoverable after this runs. See
docs/operations.md's upgrade procedure.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_plants_image_asset"
down_revision: str | None = "0001_plants_initial"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE plants.plant ADD COLUMN image_asset_id UUID NULL")
    op.execute("ALTER TABLE plants.plant DROP COLUMN image_path")
    op.execute("ALTER TABLE plants.plant DROP COLUMN image_content_type")
    op.execute("ALTER TABLE plants.plant DROP COLUMN image_updated_at")


def downgrade() -> None:
    op.execute("ALTER TABLE plants.plant ADD COLUMN image_path TEXT NULL")
    op.execute("ALTER TABLE plants.plant ADD COLUMN image_content_type TEXT NULL")
    op.execute("ALTER TABLE plants.plant ADD COLUMN image_updated_at TIMESTAMPTZ NULL")
    op.execute("ALTER TABLE plants.plant DROP COLUMN image_asset_id")
