from disp.core.contract import (
    ClientNavSpec,
    ModuleManifest,
    NotificationTypeSpec,
    ScheduledJobSpec,
    TileNavSpec,
    TileSize,
    TileSpec,
)

MANIFEST = ModuleManifest(
    domain="notes",
    name="Notes",
    version="1.0.0",
    description="Quick personal notes with pinning and full-text search.",
    dependencies=(),
    tiles=(
        TileSpec(
            key="notes.latest",
            title="Latest notes",
            description="Your most recent notes",
            size=TileSize.MEDIUM,
            refresh_seconds=120,
            order=10,
            nav=TileNavSpec(label="All notes"),
        ),
    ),
    client_nav=ClientNavSpec(
        label="Notes",
        icon="sticky-note",
        order=10,
        routes=("", "{note_id}"),
    ),
    settings_panels=(),
    scheduled_jobs=(
        ScheduledJobSpec(
            name="notes.purge_deleted",
            cron="30 3 * * *",
            description="Hard-delete notes soft-deleted over 30 days ago",
        ),
    ),
    # This notification type exists only to exercise the manifest contract;
    # nothing in this release actually sends a notes.reminder notification.
    notification_types=(
        NotificationTypeSpec(
            key="notes.reminder",
            title="Note reminder",
            description="Sent when a pinned note is stale",
        ),
    ),
)
