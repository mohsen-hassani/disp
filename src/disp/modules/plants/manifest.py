from pydantic import BaseModel, ConfigDict, Field

from disp.core.contract import (
    ModuleManifest,
    NotificationTypeSpec,
    ScheduledJobSpec,
    SettingsPanelSpec,
    TileSize,
    TileSpec,
)


class PlantsSettingsSchema(BaseModel):
    """Per-user knobs for the daily reminder.

    The cron itself is fixed by the manifest (a ScheduledJobSpec's cron is
    bound once at wire time and cannot be per-user), so the job runs for
    everyone and each user's preference is applied inside it.
    """

    model_config = ConfigDict(extra="forbid")

    daily_push: bool = Field(
        default=True,
        title="Daily reminder",
        description="Send a push notification each morning listing the plant care that is due.",
    )
    include_upcoming_days: int = Field(
        default=0,
        ge=0,
        le=14,
        title="Look ahead (days)",
        description="Also mention actions falling due within this many days. 0 = only what is due.",
    )


MANIFEST = ModuleManifest(
    domain="plants",
    name="Plants",
    version="1.0.0",
    description="Plant care schedules with recurring watering, feeding and repotting reminders.",
    dependencies=(),
    tiles=(
        TileSpec(
            key="plants.due",
            title="Plant care",
            description="Watering and feeding due today",
            size=TileSize.MEDIUM,
            refresh_seconds=300,
            order=20,
        ),
    ),
    settings_panels=(
        SettingsPanelSpec(
            key="plants.reminders",
            title="Plant reminders",
            description="Control the daily plant care reminder.",
            schema_model=PlantsSettingsSchema,
            scope="user",
        ),
    ),
    scheduled_jobs=(
        ScheduledJobSpec(
            name="plants.daily_check",
            cron="0 7 * * *",
            description="Check every plant's care intervals and notify about anything due",
        ),
    ),
    notification_types=(
        NotificationTypeSpec(
            key="plants.care_due",
            title="Plant care due",
            description="Sent each morning when a plant needs watering, feeding or repotting.",
        ),
    ),
)
