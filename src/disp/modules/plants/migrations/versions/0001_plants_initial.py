"""plants initial schema

Revision ID: 0001_plants_initial
Revises:
Create Date: 2026-08-01

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_plants_initial"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS plants")

    op.execute("""
        CREATE TABLE plants.plant (
            id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id            UUID        NOT NULL,
            name               TEXT        NOT NULL,
            description        TEXT,
            care_notes         TEXT,
            image_path         TEXT,
            image_content_type TEXT,
            image_updated_at   TIMESTAMPTZ,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at         TIMESTAMPTZ,
            CONSTRAINT ck_plants_name_len
                CHECK (char_length(name) BETWEEN 1 AND 120),
            CONSTRAINT ck_plants_description_len
                CHECK (description IS NULL OR char_length(description) <= 2000),
            CONSTRAINT ck_plants_care_notes_len
                CHECK (care_notes IS NULL OR char_length(care_notes) <= 20000)
        )
    """)
    op.execute("""
        CREATE INDEX ix_plants_plant_user_created
            ON plants.plant (user_id, created_at DESC)
            WHERE deleted_at IS NULL
    """)

    op.execute("""
        CREATE TABLE plants.care_interval (
            id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            plant_id      UUID        NOT NULL
                              REFERENCES plants.plant (id) ON DELETE CASCADE,
            name          TEXT        NOT NULL,
            interval_days INTEGER     NOT NULL,
            next_due_on   DATE        NOT NULL,
            last_done_on  DATE,
            active        BOOLEAN     NOT NULL DEFAULT true,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_plants_interval_name_len
                CHECK (char_length(name) BETWEEN 1 AND 80),
            CONSTRAINT ck_plants_interval_days_range
                CHECK (interval_days BETWEEN 1 AND 3650)
        )
    """)
    op.execute("CREATE INDEX ix_plants_interval_plant ON plants.care_interval (plant_id)")
    op.execute("""
        CREATE INDEX ix_plants_interval_due
            ON plants.care_interval (next_due_on)
            WHERE active
    """)

    # interval_id is SET NULL rather than CASCADE, and action_name is a
    # snapshot: deleting or renaming an interval must never rewrite what the
    # calendar shows for a month that has already happened.
    op.execute("""
        CREATE TABLE plants.care_log (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            plant_id    UUID        NOT NULL
                            REFERENCES plants.plant (id) ON DELETE CASCADE,
            interval_id UUID
                            REFERENCES plants.care_interval (id) ON DELETE SET NULL,
            user_id     UUID        NOT NULL,
            action_name TEXT        NOT NULL,
            due_on      DATE        NOT NULL,
            completed_on DATE       NOT NULL,
            days_late   INTEGER     NOT NULL,
            note        TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_plants_log_action_name_len
                CHECK (char_length(action_name) BETWEEN 1 AND 80),
            CONSTRAINT ck_plants_log_note_len
                CHECK (note IS NULL OR char_length(note) <= 2000)
        )
    """)
    op.execute("""
        CREATE INDEX ix_plants_log_plant_completed
            ON plants.care_log (plant_id, completed_on DESC)
    """)
    op.execute("""
        CREATE INDEX ix_plants_log_user_completed
            ON plants.care_log (user_id, completed_on DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plants.care_log")
    op.execute("DROP TABLE IF EXISTS plants.care_interval")
    op.execute("DROP TABLE IF EXISTS plants.plant")
