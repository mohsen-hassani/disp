# M8 — settings_store.py

**Status:** Complete (a real masking bug found and fixed during M9 review — see notes)

**Scope:** `SettingsStore` (`get`/`set`/`get_all`/`delete`, Fernet encrypt/decrypt, `SettingsDecryptionError`) plus the `/api/settings/{domain}` router in the same file.

Covers TECHNICAL-SPEC.md §15 (Settings store).

---

## §15. Settings store

```python
class SettingsStore:
    async def get(self, session, *, user_id: UUID | None, domain: str,
                  key: str, default: Any = None) -> Any
    async def set(self, session, *, user_id: UUID | None, domain: str,
                  key: str, value: Any, is_secret: bool = False) -> None
    async def get_all(self, session, *, user_id: UUID | None,
                      domain: str, reveal_secrets: bool = False) -> dict[str, Any]
    async def delete(self, session, *, user_id: UUID | None,
                     domain: str, key: str) -> None
```

- Non-secret values are stored in `value_json`; secrets are `json.dumps`-ed, encoded UTF-8, encrypted with Fernet using `MYSTUFF_SETTINGS_KEY`, and stored in `value_encrypted`.
- `get_all` with `reveal_secrets=False` returns `"***"` for secrets. Only the notifier task uses `reveal_secrets=True`.
- Changing a key from non-secret to secret (or back) is allowed; `set` rewrites both columns consistently to satisfy `ck_settings_one_value`.
- Decryption failure (wrong key) MUST raise `SettingsDecryptionError`, be logged at `ERROR`, and surface as `500 settings.decryption_failed` — never as a silent `None`.
- `user_id=None` denotes a global setting; only admins may write global settings through the HTTP API.

**HTTP:**

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/api/settings/{domain}` | Caller's values for that domain, secrets masked. `404` if the domain has no registered settings panel. |
| `PUT` | `/api/settings/{domain}` | Body validated against the panel's `schema_model`. Partial update: only supplied keys change. Returns the masked result. |

## Implementation notes — the generic HTTP layer design

The spec gives exactly one concrete settings panel (`core.notifier`, §14.1/§14.3) and doesn't fully specify how a generic `schema_model`-driven HTTP router maps Pydantic field names to `SettingsStore` keys, or how it knows which fields are secret (the `SettingsPanelSpec` contract from §8.1 has no reader/writer hook, by design — it's frozen and normative). Resolved with a self-consistent, generic convention (not a spec conflict requiring a pause — an underspecified plumbing detail, same category as the daily-planner/registry wiring gap from M7/M10):

- Store key = `f"{prefix}.{field_name}"`, where `prefix` is the panel's own key with its domain removed (`"core.notifier"` → `"notifier"`).
- A field is treated as secret if its Pydantic `FieldInfo.json_schema_extra` contains `{"secret": True}` — a convention defined on the schema model itself (no contract changes needed, since `schema_model` is just `type[BaseModel]` and callers are free to add their own field metadata).
- `"***"` in a PUT payload for a secret field means "leave unchanged" (§14.3); for a secret `dict[str, str]` field it merges key-by-key rather than wholesale replacing.
- GET always decrypts server-side (to know what's set / build the masked shape) but **never** returns plaintext over HTTP — masking happens in a shared `_read_masked_panel()` helper used by both GET and the PUT response.

**Bug found and fixed:** the first draft of the GET/PUT handlers called `store.get()` directly (which always returns the fully decrypted value — by design, since `SettingsStore.get()` has no masking parameter, only `get_all()` does) and returned that raw value over HTTP for every field, including secrets. This would have leaked plaintext Apprise URLs through `GET /api/settings/core`. Caught during self-review before moving to M9, fixed by routing both handlers through `_read_masked_panel()`, and verified with a fake-store smoke test asserting the literal URL string never appears in the response.
