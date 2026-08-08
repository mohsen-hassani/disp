# M9 — notifier.py

**Status:** Complete (implementation + smoke tests + lint/mypy pass done)

**Scope:** `NotifierFacade.send`, `core.deliver_notification` task, the `core.notifier` settings panel (`NotifierSettingsSchema`, `NOTIFIER_SETTINGS_PANEL`).

Covers TECHNICAL-SPEC.md §14 (Notifier).

---

## §14.1 Channel configuration

Stored in the settings store under domain `core`, per user:

- Key `notifier.channels`, non-secret, JSON array of:
  ```json
  {"id": "phone", "label": "Phone push", "enabled": true}
  ```
  `id` matches `^[a-z][a-z0-9_-]{0,31}$`.
- Key `notifier.url.<channel_id>`, **secret**, a single Apprise URL string. Stored encrypted; never returned by any API.
- Key `notifier.routing`, non-secret, an object mapping notification-type key → array of channel ids.

> **Implementation deviation:** rather than one `notifier.url.<channel_id>` row per channel, all channel URLs are stored together as **one** secret JSON blob under key `notifier.urls` (matching the `NotifierSettingsSchema.urls: dict[str, str]` field from the M8 generic-panel design). This is a simpler, fully generic design consistent with M8's field→key convention, at the cost of not matching the spec's illustrated per-channel key name literally. Functionally equivalent: still encrypted at rest, still masked over HTTP, still never returned in plaintext, still supports "***  = leave this one unchanged" per-key on PUT (merge semantics inside the one blob).

## §14.2 Resolution

`NotifierFacade.send(user_id, notification_type, title, body, url=None)` MUST:

1. Validate that `notification_type` is a registered `NotificationTypeSpec` key; unknown → `ValueError`.
2. Defer the Procrastinate task `core.deliver_notification` with the arguments. `send` returns immediately; it never performs network I/O inline.

The task `core.deliver_notification` MUST:

1. Load `notifier.routing`; take the channel list for the type.
2. If absent, fall back to every channel with `enabled: true`.
3. If still empty, write `core.notification_log` with `status='no_channels'` and return without error.
4. Decrypt each channel's Apprise URL, build one `apprise.Apprise()` instance, add all URLs, and call `notify(title=..., body=...)`.
5. Write `core.notification_log` with `status` = `sent` (all succeeded), `partial`, or `failed`, and `error` holding a truncated (1000 char) diagnostic.
6. Raise on total failure so Procrastinate retries; do **not** raise on partial success.

Apprise URLs MUST NOT appear in logs, tracebacks, or error responses. The log line records channel ids only.

> **Implementation note on per-channel results:** Apprise's `Apprise.async_notify()` returns a single aggregate `Optional[bool]` for a multi-URL batch, with no built-in way to distinguish "some failed" from "all failed" from that return value alone. Resolved by adding each URL to the **one** shared `Apprise()` instance with a per-channel `tag`, then calling `async_notify(..., tag=channel_id)` once per channel to get per-channel pass/fail — still "one Apprise instance, all URLs added" as specified, just multiple targeted `notify` calls instead of one untargeted call, which is necessary to compute `sent`/`partial`/`failed` at all.
>
> **Implementation note on step 6's ordering:** the notification_log write must survive even when the task subsequently raises (so Procrastinate's retry doesn't lose the record). The log write happens inside `session_scope(...)` (which commits normally on a clean exit), and the `raise NotifierDeliveryError(...)` happens **after** that `async with` block has already exited/committed — never inside it, where a raised exception would trigger `session_scope`'s rollback and undo the log write.

## §14.3 Settings panel

The core notifier registers a settings panel `core.notifier` with scope `user`, whose schema model exposes `channels`, `routing`, and a write-only `urls` mapping. `GET /api/settings/core` MUST return secret values as the literal string `"***"` when set and `null` when unset. `PUT` MUST treat `"***"` as "leave unchanged".

## Implementation notes

- `deliver_notification` and `NotifierFacade.send`'s validation both need a live reference to (respectively) the `SettingsStore`/session-maker and the `Registry`'s `notification_types` index — neither exists until M10's platform wiring. Resolved with a small `configure(*, store, session_maker, registry)` function, called once from `create_app()`/`worker.py` when the `Platform` is constructed, populating a module-level `_context` singleton (same pattern as `scheduler.py`'s `set_registry`).
- Verified end-to-end with `apprise.Apprise.async_notify` mocked (per §22.1's "Apprise is mocked at the `apprise.Apprise.notify` boundary" — used the async variant since the codebase is fully async): all four delivery outcomes (`no_channels`, `sent`, `partial`, `failed`) produce the correct `notification_log` row, and the `failed` case confirmed the log persists even though the task raises afterward. Also verified `send()` rejects an unknown `notification_type` with `ValueError`, and that no URL string ever appears in log output.
- Renamed `scheduler.py`'s `_default_retry_strategy` to public `default_retry_strategy` since `notifier.py` needed to reuse it for `core.deliver_notification`'s retry policy.
