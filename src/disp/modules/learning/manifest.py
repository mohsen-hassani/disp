from pydantic import BaseModel, ConfigDict, Field

from disp.core.contract import (
    ClientNavSpec,
    ModuleManifest,
    NotificationTypeSpec,
    ScheduledJobSpec,
    SettingsPanelSpec,
    TileSize,
    TileSpec,
)


class LearningSettingsSchema(BaseModel):
    """§7/§21. Exactly one panel is a hard constraint, not a preference:
    `settings_store._find_panel` resolves the *first* panel whose key
    prefix matches a domain, so a second `learning.*` panel would be
    unreachable over `GET|PUT /api/settings/learning` — a core limitation
    recorded in §27, not something to fix here.
    """

    model_config = ConfigDict(extra="forbid")

    daily_study_reminder: bool = Field(
        default=False,
        title="Daily study reminder",
        description="Notify me once a day if I have an in-progress course.",
    )
    weak_point_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        title="Weak point threshold",
        description="Tags scoring below this appear in your weak points list.",
    )


# `learning.index_course` / `learning.generate_path` are deliberately absent
# from `scheduled_jobs` even though they're registered scheduler tasks: that
# field is only for cron-bound periodic jobs (Registry.wire() calls
# `register_periodic` on every entry) — these two are ad-hoc, dispatched by
# `platform.scheduler.defer()` from an HTTP route, never on a timer (§16).
# `learning.daily_nudge` (§7/§20) IS periodic, so it belongs here.
MANIFEST = ModuleManifest(
    domain="learning",
    name="Learning",
    version="1.0.0",
    description="Merge study sources into one topic index, then learn it with a generated path, "
    "quizzes and exercises.",
    dependencies=(),
    client_nav=ClientNavSpec(
        label="Learning",
        icon="graduation-cap",
        order=30,
        routes=(
            "",
            "{course_id}",
            "{course_id}/path",
            "{course_id}/items/{item_id}",
            "{course_id}/quiz/{session_id}",
            "{course_id}/exercise/{session_id}",
            "{course_id}/chat",
            "{course_id}/notes",
        ),
    ),
    tiles=(
        TileSpec(
            key="learning.next_up",
            title="Learning",
            description="Your next lesson and weakest skills",
            size=TileSize.MEDIUM,
            refresh_seconds=600,
            order=30,
        ),
    ),
    settings_panels=(
        SettingsPanelSpec(
            key="learning.study",
            title="Study preferences",
            schema_model=LearningSettingsSchema,
            scope="user",
        ),
    ),
    scheduled_jobs=(
        ScheduledJobSpec(
            name="learning.daily_nudge",
            cron="0 18 * * *",
            description="Remind users with an in-progress course.",
        ),
    ),
    notification_types=(
        NotificationTypeSpec(
            key="learning.index_ready",
            title="Course indexed",
            description="A course finished indexing and is ready to study.",
        ),
        NotificationTypeSpec(
            key="learning.study_reminder",
            title="Daily study reminder",
            description="You have an in-progress course.",
            default_enabled=False,
        ),
    ),
)
