# M18 — core file/asset service

**Status:** Not started (specification only — no code written)

**Scope:** new package `src/disp/core/files/` (`__init__.py`, `store.py`, `signing.py`, `sniff.py`,
`routes.py`, `sweep.py`, `backends/local.py`, `backends/s3.py`), a `core.assets` table + core Alembic
revision, `FileStore` on `Platform`, `DISP_FILES_*` settings, the `core.sweep_files` scheduled job,
`disp-admin files …` commands. Phase 2 ports `plants` onto it; phase 3 amends the web client.

**Covers:** no *feature* in `TECHNICAL-SPEC.md` — this is a capability the backbone spec never
described. Like `src/disp/modules/plants/TECHNICAL-SPEC.md`, this document is therefore *normative for
itself*: it is the source of truth for anything under `src/disp/core/files/`.

**Amends** `TECHNICAL-SPEC.md` §5.2, §8.4, §17.2, §17.7, §21, §22.1, §22.2 and Appendix A, and
`TECHNICAL-SPEC-WEB.md` §7.3 — see §17. It does add features nowhere in the backbone spec, but it also
*extends seven normative lists* there, and those edits are part of the milestone, not consequences of
it.

**Depends on `M21`** (error code namespace). Codes here are `core.files.*`, which is the current
three-segment shape, not a new fourth one.

When implementation lands, distil the as-built reality into `docs/files.md` and reduce this file to a
build log, the way `M00`–`M17` read today.

---

## §1. Why this exists

`plants` invented private media storage because nothing shared existed: `plants/storage.py`
(path resolution, atomic temp-file rename, stale-variant cleanup), `plants/config.py`
(magic-byte sniffing, a four-type allow-list, a 2 MiB cap), three columns on `plants.plant`
(`image_path`, `image_content_type`, `image_updated_at`), three routes, a `media:/data/media` volume,
and a bespoke backup cron in `docs/operations.md`. None of that is about plants. A second module
storing images copies all of it, and the platform acquires two divergent media mechanisms, two
backup paths, and two chances to get path-traversal and content sniffing wrong.

The goal is one interface — `platform.files` — through which any module accepts bytes from any
channel (HTTP upload, CLI, a worker job) and gets back an **asset id** and, on request, a **URL**.
Where the bytes physically live is a deployment choice the module cannot observe.

Three problems this fixes on the way, each already live in the codebase:

1. **`plants` destroys bytes inside a transaction that can still roll back.**
   `clear_plant_image` calls `remove_image(plant_id)` at `plants/service.py:683`, and `write_image`'s
   stale-variant cleanup unlinks the previous photo at `plants/storage.py:62` — both before the
   caller's commit. A rollback after either point is **unrecoverable data loss**. The milder inverse
   also exists: `plants/service.py:669` writes the new file inside the same uncommitted transaction, so
   a later failure leaves an orphaned file, or a rollback leaves `plant.image_path` pointing at bytes
   whose row was discarded. §8 makes the ordering an invariant instead of an accident, and I2 exists
   specifically for `:683`.

2. **`plants` buffers the entire upload before checking its size.** `plants/router.py:203` passes
   `data=await file.read()` and the length check is at `plants/service.py:650`. A 5 GB POST is consumed in
   full before being rejected with 413. (Starlette spools past ~1 MiB to a temp file, so it is
   disk rather than RAM for large uploads — the point stands.) §7.2 makes the limit apply *during* the
   stream.

3. **Plant photos do not render at all today, and the failure is silent.**
   `clients/web/src/components/plants/PlantThumbnail.tsx:38` is a plain `<img src={imageUrl}>` pointed
   at `plant.image_url`, which the server sets to `/api/plants/{id}/image` (`plants/service.py:157`).
   That route requires `current_user`, and `core/auth/dependencies.py:156-167` accepts **only** an
   `Authorization: Bearer` header — the refresh cookie is `Path=/api/auth` and is never sent there. A
   browser attaches neither to an image request, so every photo 401s. `PlantThumbnail`'s
   `onError` handler (`:42`) then swaps in the `Sprout` placeholder that was written for the
   database-only-restore case, and the auth failure is indistinguishable from "this plant has no
   photo". Signed URLs (§9) make the existing markup work, for every module at once.

   > An earlier draft of this milestone described a `usePlantImageUrl.ts` blob workaround here. That
   > hook was deleted in `33d2b0f` and the plants client rebuilt without it in `1f64607`. The
   > *reasoning* was right — a browser will not attach a JS-held bearer token to an `<img>` — but it
   > was attached to a file that no longer exists, inherited from
   > `src/disp/modules/plants/TECHNICAL-SPEC.md` §17.4, which is also stale. Phase 3 is a **bug fix**,
   > not a simplification.

**The central design decision** is that the signing layer lives in *core*, not in the storage
backend. Presigned URLs are an HMAC over `(object id, expiry)` that a server verifies before
streaming bytes; S3 popularised the pattern but does not own it. Signing in core means the local
filesystem backend has exactly the same URL ergonomics as S3, and switching between them is a config
change no module and no client can detect. Running MinIO on a single-host deployment to obtain
semantics core can provide directly is operational weight for nothing.

## §2. Concepts and invariants

- **Asset** — one stored object plus its metadata row. Assets are **immutable**: there is no
  overwrite operation. Replacing a plant photo creates a new asset and drops the reference to the
  old one. This is what makes `ETag`/`immutable` caching and long-lived signed URLs safe — a URL can
  never resolve to different bytes than it did a minute ago — and it makes concurrent replacement a
  non-problem.
- **Backend** — where bytes live (`local`, `s3`). Selected once per deployment.
- **Storage key** — the backend-relative key for an asset's bytes, derived entirely from
  platform-generated values (§5).
- **Owner** — the `core.users` row an asset is billed to, for quota and for the authenticated
  fallback route. **The owner is not an ACL.** Whether a given user may see a given plant's photo is
  the `plants` module's judgement, made before it mints a URL (§9.4). Core never learns what a plant
  is.

Invariants, each of which a test must pin:

- **I1** Bytes are written before the row referencing them is committed.
- **I2** Bytes are never deleted inside a transaction. `delete()` sets `deleted_at`; only the sweeper
  removes objects.
- **I3** The sweeper deletes *objects* that have no row, and *rows* that were soft-deleted. It
  **never** deletes a row because its object is missing — see §15.3 for the restore scenario that
  rule protects.
- **I4** No part of a storage key ever derives from client input.
- **I5** What is served back is decided by what the bytes are, never by a declared `Content-Type`.
- **I6** Only a type core positively identified may be served `Content-Disposition: inline`.
  Everything else is `attachment` (§7.1).

## §3. Configuration

Added to core `Settings` (`src/disp/core/config.py`, env prefix `DISP_`). Note `model_config` sets
`extra="forbid"` (`config.py:10`), so every one of these must exist as a field on the class — an env
var alone will not do, unlike the module-owned `DISP_PLANTS_*` settings, which pydantic-settings
ignores by prefix.

| Field | Env | Default | Notes |
|---|---|---|---|
| `files_backend` | `DISP_FILES_BACKEND` | `local` | `local` \| `s3` |
| `files_root` | `DISP_FILES_ROOT` | `var/media` | local backend only |
| `files_max_bytes` | `DISP_FILES_MAX_BYTES` | `26_214_400` (25 MiB) | hard ceiling; an `AcceptSpec` may be stricter, never looser |
| `files_url_ttl_seconds` | `DISP_FILES_URL_TTL_SECONDS` | `3600` | default signed-URL lifetime, `ge=60, le=86400` |
| `files_sweep_grace_seconds` | `DISP_FILES_SWEEP_GRACE_SECONDS` | `86400` | §8.3 |
| `files_sweep_cron` | `DISP_FILES_SWEEP_CRON` | `30 4 * * *` | plain `str`, unvalidated — matches `daily_planner_cron` (`config.py:27`) |
| `files_s3_bucket` | `DISP_FILES_S3_BUCKET` | `""` | |
| `files_s3_endpoint_url` | `DISP_FILES_S3_ENDPOINT_URL` | `None` | unset for AWS; set for R2/B2/MinIO |
| `files_s3_region` | `DISP_FILES_S3_REGION` | `auto` | |
| `files_s3_access_key_id` | `DISP_FILES_S3_ACCESS_KEY_ID` | `SecretStr("")` | |
| `files_s3_secret_access_key` | `DISP_FILES_S3_SECRET_ACCESS_KEY` | `SecretStr("")` | |
| `files_s3_prefix` | `DISP_FILES_S3_PREFIX` | `""` | key prefix inside the bucket |
| `files_s3_force_path_style` | `DISP_FILES_S3_FORCE_PATH_STYLE` | `true` | MinIO requires it; R2/B2 tolerate it |
| `files_s3_native_presign` | `DISP_FILES_S3_NATIVE_PRESIGN` | `false` | §10 — read its CSP warning before enabling |

A `model_validator(mode="after")` MUST reject `files_backend="s3"` with an empty bucket or empty
credentials, in the style of the existing `_validate_production_cookie_secure` (`config.py:75-79`).
Failing at startup is the point: a deployment that silently falls back to local disk and then loses a
volume is worse than one that refuses to boot.

**`files_root`'s default is deliberately relative**, matching `DISP_PLANTS_MEDIA_ROOT`'s
`var/media/plants`. Every path comparison under it MUST be resolved-to-resolved. This is not
hypothetical: a bug where `write_image` deleted the file it had just written survived the entire unit
suite because `tmp_path` is absolute and pre-resolved, and only appeared against the real server
(`CLAUDE.md`, plants gotchas; the regression is pinned by
`tests/modules/test_plants.py:794`). §14 requires the equivalent shipped-default-shape test here,
including the `monkeypatch.chdir` that test uses — a relative *string* with an absolute CWD does not
reproduce it.

**`DISP_BASE_URL` is not used by this milestone.** Signed URLs are relative (§9.1). `base_url`
(`config.py:21`) exists for invite links and stays that way.

`DISP_PLANTS_MEDIA_ROOT` and `DISP_PLANTS_MAX_IMAGE_BYTES` disappear in phase 2 (§12).

## §4. Data model — `core.assets`

```sql
CREATE TABLE core.assets (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id     UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
    domain            TEXT        NOT NULL,
    purpose           TEXT        NOT NULL,
    content_type      TEXT        NOT NULL,
    byte_size         BIGINT      NOT NULL,
    sha256            TEXT        NOT NULL,
    original_filename TEXT,
    backend           TEXT        NOT NULL,
    storage_key       TEXT        NOT NULL,
    attributes        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at        TIMESTAMPTZ,
    CONSTRAINT ck_assets_domain     CHECK (domain ~ '^[a-z][a-z0-9_]{1,31}$'),
    CONSTRAINT ck_assets_purpose    CHECK (purpose ~ '^[a-z][a-z0-9_]{1,63}$'),
    CONSTRAINT ck_assets_byte_size  CHECK (byte_size > 0),
    CONSTRAINT ck_assets_sha256     CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT uq_assets_backend_storage_key UNIQUE (backend, storage_key)
);
CREATE INDEX ix_assets_owner  ON core.assets (owner_user_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX ix_assets_lookup ON core.assets (domain, purpose)               WHERE deleted_at IS NULL;
CREATE INDEX ix_assets_sweep  ON core.assets (deleted_at)                    WHERE deleted_at IS NOT NULL;
```

**The `id` default is `gen_random_uuid()` for a direct SQL insert, but the ORM model MUST also set
`default=uuid.uuid4`** so the id exists in Python before any INSERT. §5 explains why this is
load-bearing rather than stylistic. Table conventions otherwise follow `core/models.py`: `SCHEMA`
constant in `__table_args__`, `TIMESTAMPTZ` with `server_default=func.now()`, `ck_<table>_<what>`
constraint names, partial indexes via `postgresql_where`. `JSONB` is already in use at
`core/models.py:258-260`.

**The JSONB column is `attributes`, not `metadata`.** `metadata` is a reserved attribute on
SQLAlchemy's `DeclarativeBase` (`Base.metadata`); a mapped column of that name fails at class
definition. Same family of trap as `SettingsPanelOut.schema_` shadowing `pydantic.BaseModel.schema()`
(`CLAUDE.md`, settings-panel section) — write it down rather than rediscovering it.

`domain` and `purpose` are the module's own labels (`"plants"` / `"plant_photo"`). `purpose` is what
later drives per-kind quotas, retention, and variant policy without a schema change.

**`domain` is caller-supplied and core cannot verify it.** `put()` takes it as an argument; nothing
proves the `plants` module passed `"plants"`. This is accepted, not overlooked — verifying it would
mean core inspecting its caller's stack or the facade being per-module, and the platform's trust model
already assumes modules are in-tree code reviewed together. It is recorded here so the next reader
does not mistake `domain` for a security boundary. It is a *label*, and the `ck_assets_domain` check
constrains only its shape.

The `owner_user_id` FK cascades: deleting a user drops their asset rows, and the sweeper then reaps
the objects on its next pass (§8.3, case B). Eight core tables already carry a `core.users` FK
(`core/models.py:88,95,121,169,208,214,250,287`), so this is unremarkable for a *core* table. The
invariant it must not break is the one about **modules**: a module referencing an asset stores a bare
`uuid` column with no cross-schema FK, exactly as `plants.plant.user_id` already does per §6.1 of the
backbone spec.

> **Cascade asymmetry, deliberate but worth knowing.** `delete()` soft-deletes with a 24-hour grace
> (§8.2), but `ON DELETE CASCADE` hard-deletes an asset row the instant its owner is deleted. A
> mistaken user deletion is therefore unrecoverable after one sweep, where a mistaken asset deletion
> is recoverable for a day. Accepted because deleting a user is already an irreversible operation with
> no undo anywhere else in the platform; changing it here would imply a soft-delete story for users
> that does not exist.

The ORM model `Asset` goes in `src/disp/core/models.py` but is **not** part of the module-facing
surface (§11) — modules receive the `StoredFile` DTO, never the mapped class. Note this is currently
convention, not enforcement: `tests/core/test_boundaries.py` gates `disp.core.auth` and `disp.core.db`
but says nothing about `disp.core.models`, which is how `notes/service.py:16` came to import
`disp.core.models.User`. §11 pins the new surface; an `ALLOWED_MODELS_NAMES` would be the general fix
and is out of scope here.

## §5. Storage key layout

```
<domain>/<purpose>/<YYYY>/<MM>/<asset_id><ext>
plants/plant_photo/2026/08/9c3f…-e21a.jpg
```

`<ext>` comes from core's sniffed-type→extension table. **No component derives from client input**
(I4) — `original_filename` is stored as metadata and used only for `Content-Disposition`, never as a
path. The local backend keeps `plants/storage.py`'s belt-and-braces `_ensure_inside(root, candidate)`
check anyway (`storage.py:12`), on the same reasoning its header comment already gives: the guard is
there for the day the first sentence stops being true.

**`<asset_id>` and the date shard are generated in Python, not by the database.** This is forced by
I1: bytes are written before the row is committed, and streaming to the backend needs the key
*before* the first chunk is consumed. A `gen_random_uuid()` default is not known until INSERT, so
the id must come from `uuid.uuid4()` (§4) and the date from the ingest timestamp the request already
has. The DB defaults stay as a fallback for hand-written SQL.

A consequence to accept rather than fix: an upload straddling midnight on the last day of a month can
land a key under a different `YYYY/MM` than its own `created_at`. Harmless, because **the key is a
stored column, not a derived one** — nothing recomputes it, so nothing can disagree with it. A future
layout change likewise affects new assets only and needs no backfill.

Date sharding keeps a local directory from accumulating tens of thousands of sibling entries and
makes an S3 bucket human-navigable.

## §6. `StorageBackend` protocol

```python
class StorageBackend(Protocol):
    name: str  # "local" | "s3", persisted into assets.backend

    async def write(self, key: str, chunks: AsyncIterator[bytes]) -> None: ...
    async def read(self, key: str) -> AsyncIterator[bytes]: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def iter_objects(self, prefix: str = "") -> AsyncIterator[tuple[str, datetime]]: ...
    def native_signed_url(self, key: str, *, content_type: str, expires_in: int) -> str | None: ...
```

`write` MUST be atomic-or-absent: a crash mid-write leaves either the complete object or nothing, never
a truncated object being served. `iter_objects` yields `(key, last_modified)` and exists solely for the
sweeper. `native_signed_url` returns `None` on any backend that cannot presign — the local one always
does, and §10's redirect path is skipped accordingly.

### §6.1 Local backend

Write to `<root>/<key>.<random>.tmp` in the destination directory, `fsync`, then `Path.replace()` onto
the final name — the rename is atomic within a filesystem, which is why the temp file must be a
sibling and not in `/tmp`. `delete()` uses `missing_ok=True`: the sweeper must be idempotent.
`iter_objects` walks the tree with `os.scandir`, skipping `*.tmp`.

This generalises `plants/storage.py`, but **three of these are improvements, not ports** — do not
assume the existing code already does them:

| | `plants/storage.py` today | Here |
|---|---|---|
| Durability | `temp.write_bytes(data)` then `temp.replace(target)`, **no `fsync`** (`:56-58`) | `fsync` before the rename |
| Temp name | deterministic `.<uuid>.<ext>.tmp` (`:56`) — two concurrent uploads for one plant collide | `<key>.<random>.tmp` |
| Delete | `if path.exists(): path.unlink()` (`:62`, `:66-69`) — TOCTOU-racy | `unlink(missing_ok=True)` |

### §6.2 S3 backend

`aioboto3` behind an **optional dependency group** (`[project.optional-dependencies] s3 = ["aioboto3>=13"]`),
imported lazily *inside* `backends/s3.py` so `import disp` works, and the production image builds, with
the extra absent. Selecting `files_backend="s3"` without the extra installed MUST fail at startup with
a message naming the extra, not with a bare `ModuleNotFoundError` three requests later.

> `pyproject.toml` has **no `[project.optional-dependencies]` table today** — it uses PEP 735
> `[dependency-groups]` for dev deps. This would be the first. `uv sync` does not install optional
> extras by default, which is what makes §14's clean-skip requirement load-bearing rather than
> theoretical. Note also `[[tool.mypy.overrides]] module = "disp.core.*"` is `strict = true`, so the
> lazily-imported client needs real types or a scoped ignore.

Uploads under 5 MiB use `put_object`; larger ones use a multipart upload so memory stays bounded —
this is the only place the 25 MiB ceiling of §3 is not the operative limit, and it is what makes raising
that ceiling later a config change rather than a rewrite. `native_signed_url` delegates to
`generate_presigned_url("get_object", …)`, pinning `ResponseContentType` and
`ResponseContentDisposition` so a presigned response carries the same headers §10 sets on the streamed
path.

Works unmodified against AWS, Cloudflare R2, Backblaze B2, and MinIO. `files_s3_force_path_style`
defaults `true` because MinIO requires it and the hosted providers accept it.

## §7. `FileStore` — the module-facing facade

Constructed once in `create_app()`/`worker.py` and hung on `Platform` as `files`, beside `store`,
`notifier`, and `scheduler`. A request-scoped FastAPI dependency `get_file_store(request)` reads
`request.app.state.platform.files`, mirroring `settings_store._get_store` (`settings_store.py:188-189`).

**There is a third construction context the facade must serve: the CLI.** `disp-admin` has no
`Platform` — `cli_admin.py:32-33` builds its own engine and session maker per command. `disp-admin
files adopt`/`verify` (§12, §15.3) therefore need a `FileStore.from_settings(settings)` classmethod
that constructs a backend directly, and `create_app()`/`worker.py` should use it too rather than
duplicating wiring three ways.

```python
stored: StoredFile = await platform.files.put(
    session,
    owner=user,                    # CurrentUser or a UUID (worker context)
    domain="plants",
    purpose="plant_photo",
    source=upload,                 # UploadFile | bytes | AsyncIterator[bytes]
    filename=upload.filename,
    accept=ACCEPT_IMAGES,
    attributes={"origin": "web"},  # optional, module-defined
)
plant.image_asset_id = stored.id
```

| Method | Contract |
|---|---|
| `put(session, *, owner, domain, purpose, source, filename=None, accept, attributes=None) -> StoredFile` | Streams, validates, writes bytes, adds the row to `session`. Does **not** commit — the caller's transaction owns it (I1). |
| `get(session, asset_id) -> StoredFile \| None` | `None` for unknown or soft-deleted. |
| `open(session, asset_id) -> AsyncIterator[bytes]` | Streams bytes. `core.files.not_found` if the row is unknown or soft-deleted; `core.files.missing_object` if the row exists but the object does not. |
| `delete(session, asset_id) -> None` | Sets `deleted_at`. Idempotent. Never touches bytes (I2). |
| `signed_url(asset_id, *, ttl=None) -> str` | Pure function of the asset id and the bucketed expiry (§9.1). No I/O, no DB access. |
| `usage(session, *, owner=None, domain=None) -> UsageSummary` | Row count and byte total, for quotas and the admin view. |

Two signatures differ from the obvious reading and the difference matters:

- **`open` takes a session.** It cannot distinguish "no such asset" from "row present, bytes gone"
  without reading the row, and that distinction is the whole point of §15.3 — one is a 404 for a
  thing that never existed, the other is an alert that a volume did not mount.
- **`signed_url` takes an id, not a `StoredFile`.** §9.1 defines the signature as a function of id and
  expiry only. Requiring the DTO would force a database read to mint a URL for an id the caller
  already holds.

`StoredFile` is a frozen dataclass: `id`, `domain`, `purpose`, `content_type`, `byte_size`, `sha256`,
`original_filename`, `created_at`. Deliberately not the ORM model — a module that can reach `Asset`
can reach every other user's assets with one `select()`.

Errors are `AppError`s in the platform's RFC 9457 shape, coded `core.files.*` — three segments, per
`ERROR_CODE_RE` (`core/errors.py`, `M21`):

| Code | Status |
|---|---|
| `core.files.empty_upload` | 400 |
| `core.files.too_large` | 413 |
| `core.files.unsupported_type` | 415 |
| `core.files.not_found` | 404 |
| `core.files.missing_object` | 404 |
| `core.files.url_expired` | 403 |
| `core.files.forbidden` | 403 |

Modules surface these directly; a module MUST NOT re-code them into its own namespace, so a client
can handle "file too large" once rather than once per domain.

> **No `quota_exceeded` code.** §16 puts quota *enforcement* out of scope, so nothing could raise it,
> and Appendix A means what it says: "every code the API **may** emit". Registering a code nothing
> emits is how `core.settings.decryption_failed` ended up with a live client branch and no server that
> ever sends it (`M21`, bugs found). When enforcement lands, the status is `507` or `403` — not `413`,
> which is about *this request's* payload, not the account total.

### §7.1 Accept specs and content handling

```python
@dataclass(frozen=True)
class AcceptSpec:
    content_types: frozenset[str]
    max_bytes: int

ACCEPT_IMAGES    = AcceptSpec(frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"}),
                              5 * 1024 * 1024)
ACCEPT_DOCUMENTS = AcceptSpec(frozenset({"application/pdf", "text/plain", "text/markdown",
                                         "text/html", "application/x-subrip"}),
                              25 * 1024 * 1024)
```

`max_bytes` is clamped to `settings.files_max_bytes` — a module can tighten the platform limit, never
loosen it. `plants` passes `ACCEPT_IMAGES` with `max_bytes=2 * 1024 * 1024` to keep today's cap.

**The safety gate is on serving, not on accepting.** This is the one substantive design change from
the first draft of this milestone, and the reasoning generalises past this feature.

Sniffing — identifying a file from its magic bytes rather than its declared `Content-Type` — is
possible only for formats that write a signature. `image/jpeg` starts `FF D8 FF`; `application/pdf`
starts `%PDF-`. Text formats have none, by definition: there is no byte sequence illegal in a `.txt`
file, so nothing distinguishes plain text from Markdown from HTML from SRT. Sniffability is therefore
not a property worth gating *acceptance* on — it is what licenses an **inline render**. Two gates:

**Accept gate.** The type is in a core-owned table, either

- *sniffable* — `image/jpeg`, `image/png`, `image/webp`, `image/gif`, `application/pdf`; identified
  from content and rejected if the bytes disagree (I5); or
- *text family* — `text/plain`, `text/markdown`, `text/html`, `application/x-subrip`; validated by a
  strict UTF-8 decode of the stream.

A module still cannot invent a type: it picks from this table, which is what stops the store becoming
an arbitrary-file host.

**Serve gate (I6).** Only a sniffed, known-safe type may carry `Content-Disposition: inline` — in
practice the four image types. Everything else, text family included, is `attachment`,
unconditionally, alongside §10's `X-Content-Type-Options: nosniff` and
`Content-Security-Policy: default-src 'none'; sandbox`.

This is what makes unsniffable types safe to store. A downloaded file cannot execute against the
platform's origin, and the origin is inside the client's trust boundary — `security-headers.conf:11`
is `default-src 'self'`, so a rendered HTML asset containing `<script>` would be same-origin stored
XSS.

Two notes on the reasoning:

- **HTML is the same hazard as SVG, and the first draft banned only SVG.** Worse, valid HTML *is* the
  dangerous case, so no amount of validation helps — validation and safety pull in opposite
  directions. Making the rule a mechanism (`inline` requires a positive identification) rather than a
  ban-list means the next type added is safe by default rather than safe by remembering.
- **SVG is excluded automatically** — it is unsniffable XML text, so it can never be served inline
  under I6. Keep it off the accept table too, but as belt-and-braces; the ban is no longer the
  protection.

Sniffing moves wholesale from `plants/config.py` into `core/files/sniff.py`, keeping its magic-prefix
table and its RIFF/WebP special case (`config.py:53-61`, which needs 12 bytes — the 16-byte sniff
buffer in §7.2 is sufficient).

`ACCEPT_DOCUMENTS`' text family is what `M20`/learning needs: its DDL commits to five source types
(`src/disp/modules/learning/TECHNICAL-SPEC.md:312-313`) of which four are unsniffable.

### §7.2 Streaming and limits

`put` consumes `source` in 64 KiB chunks and, in one pass: buffers the first chunk to sniff the type
(16 bytes suffice), rejects on the first byte past `max_bytes` **without consuming the rest of the
request body**, updates a `hashlib.sha256`, and forwards chunks to `backend.write`. Peak memory is one
chunk plus the sniff buffer regardless of upload size, for every accepted type.

Text-family validation is an incremental UTF-8 decode over the same chunk stream
(`codecs.getincrementaldecoder`), not a buffer-then-decode, so it does not compromise the guarantee.

Rejecting mid-stream is the fix for problem 2 in §1. A test MUST assert that a payload exceeding the
limit is rejected without the backend ever receiving a `write` call — asserting only on the 413 status
would pass against today's buffer-everything implementation too, and prove nothing. (There is
currently no HTTP-level image test in `plants` at all; every case in `tests/modules/test_plants.py:773`
onward calls `service.*` directly.)

## §8. Lifecycle: the two-system problem

A filesystem write and a database commit are not one transaction, and no amount of care makes them
one. The design chooses which way failures fall.

### §8.1 Create

Bytes first, row second, both before the caller commits (I1). A rollback after `put` leaves an object
with no row — wasted disk, reaped by the sweeper. The inverse (a row with no object) is a broken
image, and is what this ordering prevents. §5's Python-side id generation is what makes "bytes first"
possible at all.

### §8.2 Delete

`delete()` sets `deleted_at` and returns (I2). Removing bytes inside a transaction that can still roll
back is unrecoverable data loss — precisely what `plants/service.py:683` does today; leaving them for a
sweeper costs disk for a day. Failures land on the side of wasted disk, always.

### §8.3 The sweeper — `core.sweep_files`

> The name is `core.sweep_files`, **not** `core.files.sweep`. `ScheduledJobSpec.name` is validated
> against `KEY_RE = ^[a-z][a-z0-9_]{1,31}\.[a-z][a-z0-9_]{1,63}$` (`contract.py:17`) — exactly one dot.
> Note this is the *manifest key* namespace, which is two segments; the three-segment
> `core.files.<error>` codes in §7 are the *error code* namespace and a different regex entirely
> (`CLAUDE.md`, "Error codes are three segments").

**Registration takes three edits, not one.** `Registry.register_core_scheduled_job` is a one-line
`append` to a list (`registry.py:221-222`); it schedules nothing. `core.daily_planner`'s cron is
actually bound by a decorator pair on the module-level `procrastinate.App`:

```python
# src/disp/core/scheduler.py:81
@app.periodic(cron=get_settings().daily_planner_cron)
@app.task(name="core.daily_planner", retry=default_retry_strategy(3))
```

So `core.sweep_files` needs:

1. a decorated task in `scheduler.py` (or a module imported at app/worker startup),
2. `register_core_scheduled_job(...)` in `app.py:143`, **and**
3. the same call again in `worker.py:56` — the two are duplicated verbatim today, and a core builtin
   registered in only one is invisible to the other.

Note `@app.periodic(cron=get_settings().daily_planner_cron)` evaluates at **import time** through the
`lru_cache`d `get_settings()`. A `files_sweep_cron` read the same way is awkward to override in tests;
plan for that rather than discovering it.

Two passes, both bounded by `files_sweep_grace_seconds` (default 24 h):

- **A — soft-deleted rows.** `deleted_at < now() - grace` → delete the object, then the row. Grace
  exists so a mistaken delete is recoverable by clearing `deleted_at` within a day.
- **B — orphaned objects.** `iter_objects()` keys absent from `core.assets` **and** whose
  `last_modified < now() - grace` → delete the object. The grace period is load-bearing here: without
  it the sweeper would race an in-flight `put` whose transaction has not yet committed and delete a
  perfectly good upload.

**Pass B never deletes a row, and no pass ever deletes a row because its object is missing** (I3).
§15.3 explains the restore scenario that would otherwise destroy the metadata for an entire library.

Every pass logs counts (`swept_rows`, `swept_objects`, `skipped_in_grace`) and MUST be safe to run
concurrently with itself — `delete()` is `missing_ok` on both backends.

## §9. Signed URLs

### §9.1 Format

```
/api/files/{asset_id}?exp={unix_seconds}&sig={urlsafe_b64_no_padding}
sig = HMAC-SHA256(key, f"v1:{asset_id}:{exp}")
```

The `v1:` prefix inside the signed message allows a format change later without accepting old
signatures under new rules.

**The URL is relative, not absolute.** An earlier draft prefixed `{base_url}`. That breaks the web
client: `TECHNICAL-SPEC-WEB.md` §2.1 requires relative URLs and forbids an API base from
configuration, and `DISP_BASE_URL` is not the serving origin under `pnpm dev` (:5173 proxy), `pnpm
preview`, or an e2e run (:8000) — an absolute URL in any of those is cross-origin and blocked by
`img-src 'self'` (`security-headers.conf:11`). Today's `image_url` is already relative
(`plants/service.py:157`); keep it that way.

**`exp` is bucketed, not "now + ttl".** Compute `exp = ceil(now / ttl) * ttl`. A naive expiry makes
every mint a different query string, so every parent-query refetch — 30 seconds for
`plantDetailQueryOptions` and `plantsListInfiniteQueryOptions` (`clients/web/src/api/queries.ts:273,295`)
— produces a fresh URL, a fresh cache key, and a full re-download, while §10's response cheerfully
claims `immutable`. Bucketing makes the URL byte-identical within a window so the browser cache
actually hits, and demotes `ETag`/`304` to the fallback it should be. A test MUST assert two mints
inside one bucket produce identical URLs.

The cost of bucketing is that a URL's real lifetime varies between `0` and `ttl` rather than being
exactly `ttl`. That is why `files_url_ttl_seconds` has a `ge=60` floor: the worst case must still be
long enough to load a page.

### §9.2 Key derivation

`key = HKDF-SHA256(ikm=settings.jwt_secret.get_secret_value(), salt=b"disp-file-url", info=b"v1", length=32)`,
computed once at startup. Deriving from `DISP_JWT_SECRET` rather than adding a required env var means
existing deployments need no new configuration, and the domain separation guarantees a file signature
can never be replayed as a token or vice versa. Rotating `DISP_JWT_SECRET` invalidates outstanding file
URLs exactly as it invalidates sessions — expected, and worth one line in `docs/operations.md`.

Verification uses `hmac.compare_digest`. A test MUST cover tampered id, tampered expiry, truncated
signature, foreign-key signature, and the expired-but-valid case.

### §9.3 What a signed URL is and is not

It is a **capability**: anyone holding the URL gets the bytes until `exp`, with no session. That is
precisely S3's presigning model, and the same tradeoff. Mitigations: a one-hour default TTL,
`Cache-Control: private` so no shared cache retains it, and the fact that minting is opt-in per call —
a module that never calls `signed_url` never exposes one, and its assets remain reachable only through
the bearer-authenticated route (§10). Modules holding genuinely sensitive files should do exactly that.

> **Forwarding a signed URL discloses the file's EXIF, including GPS.** Phone photos routinely carry
> the coordinates where they were taken, and this milestone changes a plant photo from
> "bearer-token-only" to "anyone with this link, for an hour". Stripping is out of scope by explicit
> decision (§16), not by omission — but the consequence belongs here, next to the tradeoff it
> sharpens, rather than only in a list at the end.

The signature deliberately does **not** bind a user id. Binding one would buy nothing: there is no
cookie on an `<img>` request to check it against, which is the whole reason this mechanism exists.

### §9.4 Where authorization happens

In the module, before minting. `plants.get_plant` already calls `_authorize(session, user, plant_id,
"read")` (`plants/service.py:247`); it mints the URL after that check passes and puts it in
`PlantOut.image_url` — a one-function change at `plants/service.py:157`, which every response path
already funnels through. Core's route verifies signature and expiry only. Core never learns what a
plant is, and `plants` never learns what a storage key is.

### §9.5 TTL versus client cache lifetime

A signed URL embedded in a JSON response outlives that response only until `exp`, so
`files_url_ttl_seconds` MUST exceed the client `staleTime` of any query carrying one. At the shipped
values this is already satisfied with three orders of magnitude of headroom — every plants query is
`staleTime: 30_000` against a 1 h TTL — so phase 3 needs no change here. It is stated as a constraint
because a future module with a long `staleTime` could violate it.

## §10. HTTP API — `/api/files`

Mounted in `create_app()` alongside the auth/dashboard/settings routers (`app.py:135-138`). Tag
`files`, `operation_id` `files_get` / `files_usage` per §17.7.

> **`files` must be reserved as a module domain.** `DOMAIN_RE` (`contract.py:16`) happily accepts
> `domain="files"`, and such a module's routes would mount at `/api/files` and collide with this
> router. Nothing checks today. Add a reserved-name check in `Registry.discover()` and a test.

**`GET /api/files/{asset_id}`** — two authentication paths:
- With `exp`+`sig`: verify signature and expiry. No session required. **This is the platform's first
  unauthenticated route**, and it inherits §17.6's default 300/min per IP — shared by every thumbnail
  on a page. State that limit explicitly rather than letting it be inherited by accident.
- Without: bearer auth; allowed if `owner_user_id == user.id` or the caller is an admin.

Responses carry `Content-Type` (the sniffed or validated type, never a declared one — I5),
`ETag: "<sha256>"`, `Last-Modified`, `Cache-Control: private, max-age=<remaining bucket>, immutable`
(`immutable` is honest only because assets are immutable, §2, and useful only because `exp` is
bucketed, §9.1), `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none';
sandbox`, and `Content-Disposition: inline` **only** for a sniffed image (I6) / `attachment` for
everything else. `If-None-Match` → `304`. `HEAD` is supported. `Accept-Ranges: none` — range requests
are §16.

Nothing in core streams bytes today — `grep StreamingResponse src/` is empty, and `plants` uses
`FileResponse` (`plants/router.py:177-181`). The ETag/`If-None-Match`/`304`/`HEAD` handling here is
new ground with nothing to copy.

When `files_s3_native_presign` is enabled and the backend returns a `native_signed_url`, respond `302`
to it instead of streaming. **This breaks the web client's CSP**: `clients/web/security-headers.conf:11`
sets `img-src 'self' data:`, and a redirect to a bucket host is a cross-origin image load. Enabling it
requires adding that host to `img-src`. It stays off by default for that reason — the streamed path
costs one proxy hop and keeps every URL same-origin, which is the client's §2.1 premise.

**`GET /api/files/usage`** — admin only; totals by domain, purpose, and owner.

> This route MUST be declared **above** `/{asset_id}` in the router. FastAPI matches in declaration
> order, and a `/usage` declared second is parsed as an asset id and 422s. Identical to the
> `/api/plants/due` gotcha, which carries its own in-code warning at `plants/router.py:39-41`.

**There is deliberately no generic `POST /api/files`.** Uploads go through the owning module's own
route, so authorization and attachment to a parent record happen in one transaction. A generic upload
endpoint would create assets belonging to nothing, needing their own orphan policy and their own
"who may upload what" answer — two problems this design does not otherwise have.

## §11. Module contract and boundaries

Public surface of `disp.core.files`, importable by any module:
`FileStore`, `StoredFile`, `AcceptSpec`, `ACCEPT_IMAGES`, `ACCEPT_DOCUMENTS`, `UsageSummary`.

`tests/core/test_boundaries.py` gains an `ALLOWED_FILES_NAMES` allow-list enforcing exactly that list,
in the same shape as `ALLOWED_AUTH_NAMES` (`:20-31`) and `ALLOWED_DB_NAMES` (`:41`). Pinning the
surface deliberately is the point — today a module could import anything from `disp.core.files` simply
because the test does not mention it, which is how `disp.core.models.User` came to be imported by
`notes/service.py:16` without a decision ever being taken. (Leave that import alone; it is out of scope
here, but it is the precedent for why the new surface gets pinned on day one.)

Submodules (`disp.core.files.backends.*`, `signing`, `sweep`) are off-limits to modules, like
`disp.core.auth`'s internals.

## §12. Phase 2 — port `plants`

The public API is unchanged: `GET/PUT/DELETE /api/plants/{id}/image` keep working, and `PlantOut`
keeps `has_image`/`image_url` (`plants/schemas.py:76-77`). Only `image_url`'s *value* changes, from
`/api/plants/{id}/image` to a signed `/api/files/{id}?…` URL — and it starts actually rendering (§1.3).

- Delete `plants/storage.py` entirely. `plants/config.py` keeps only `PlantsSettings.max_image_bytes`
  (as an `AcceptSpec` override); `media_root`, `ALLOWED_IMAGE_TYPES`, `_MAGIC_PREFIXES`, and
  `sniff_image_type` move to core.
- Replace `image_path`, `image_content_type`, `image_updated_at` (`plants/models.py:60-64`) with
  `image_asset_id uuid` (no FK). This also retires the "path relative to the media root, never
  absolute" invariant documented at `plants/models.py:58-59`.
- `set_plant_image` becomes: authorize, `platform.files.put(...)`, `files.delete(old_asset_id)`,
  assign. All in the caller's transaction, no filesystem call in sight — which is what removes the
  `:683` and `:62` pre-commit unlinks from §1.1.
- `GET /api/plants/{id}/image` becomes a `302` to a freshly minted signed URL (authorize, mint,
  redirect) so existing clients and the CLI keep working through one hop.
- Retire `modules.plants.image_too_large` / `empty_image` / `unsupported_image` in favour of the
  `core.files.*` equivalents (§7), and update `plants/TECHNICAL-SPEC.md` §18's registry.

**Backfill.** A plants-branch migration cannot insert into `core.assets` — that is a cross-schema
write from a module's Alembic branch, and the branches have no ordering relationship. Instead ship
`disp-admin files adopt --domain plants --purpose plant_photo --root var/media/plants`, which walks
the existing media root, creates an asset per file (sniffing type, computing sha256, copying to the
configured backend's key layout), and sets `plant.image_asset_id` by matching the filename's UUID
stem. Idempotent, re-runnable, and it prints a summary rather than assuming success.

Two mechanical notes: `disp-admin` is a **flat** Typer app with one command today
(`cli_admin.py:13,21`) and no `add_typer` call — the sub-app pattern exists in `src/disp/cli/main.py:70,76`
and should be borrowed. And the command needs `FileStore.from_settings(...)` (§7), since there is no
`Platform` in CLI context.

The plants migration adds the column and drops the old three only after the operator has run `adopt` —
spelled out in `docs/operations.md` as an ordered upgrade note, not left implicit.

## §13. Phase 3 — web client amendment

**Net-additive. There is nothing to delete** — the blob-hook cleanup an earlier draft described was
already done in `33d2b0f` (§1.3).

- `PlantThumbnail.tsx` needs **no change**: it is already `<img src={imageUrl}>`, and a relative signed
  URL (§9.1) drops straight in. The observable change is that photos start appearing.
- **Handle the expired-URL case, which is not observable to JS as written.** `<img onError>` exposes no
  HTTP status — an expired signature, a missing object and a network blip are indistinguishable to it.
  The mechanism must therefore be: `onError` → invalidate the parent query (which re-mints the URL) →
  retry once, then fall back to the existing `Sprout` placeholder. Note there is no central error
  mapper to hook this into; the client has four duplicated `describe*Error` ladders
  (`api/queries.ts:122`, `plants/usePlantMutations.ts:296`, `notes/useNoteMutations.ts:208`,
  `tiles/useTileAction.ts:72`).
- Regenerate `src/api/generated/` from the new OpenAPI document. `pnpm api:check` exists
  (`package.json:20`) but is **not CI-enforced** — `.github/workflows/web-ci.yml:7-12` excludes it
  because its input `openapi.json` is a gitignored artifact — so this is a manual step requiring
  `./dev openapi` first.
- **E2E photo coverage is new work, not an amendment.** There are currently zero image assertions in
  any spec under `clients/web/tests/e2e/`. Add one: a fresh page load renders a photo with no JS blob
  involvement — the observable proof the signed-URL path works end to end. Note e2e does not run in
  `web-ci.yml` either.
- The only existing image tests are unit-level (`tests/unit/plants/PlantThumbnail.test.tsx`,
  `PhotoUpload.test.tsx`) and assert the `<img>` element renders, never that it loads — which is why
  the 401 went unnoticed.

`docs/milestones/client/M12`'s §26 out-of-scope list names "file/image attachments" as forbidden for the
*notes* screens; this does not change that.

## §14. Testing

- **One conformance suite, parametrized over both backends.** `tests/core/files/test_backends.py`
  runs identical assertions against `LocalBackend` and `S3Backend` (round-trip, overwrite-absent,
  atomic-or-absent, `delete` idempotence, `iter_objects` shape). A backend that passes it is
  substitutable; that parametrization is the single most valuable test in the milestone.
- **S3 via MinIO in testcontainers**, session-scoped, marked `@pytest.mark.s3`. The suite already
  requires Docker for Postgres, so this adds no new class of dependency — but it MUST skip cleanly
  (not error) when the `s3` extra is not installed. §22.1's "no test performs outbound network I/O"
  still holds: a testcontainer is localhost.
- **Relative-root shape test.** Configure `files_root` to the *shipped relative default* and assert a
  written object survives, mirroring `test_image_survives_a_relative_media_root`
  (`tests/modules/test_plants.py:794`). Replicate its `monkeypatch.chdir(tmp_path)` — a relative
  string with an absolute CWD does not reproduce the bug. Testing only an absolute `tmp_path` is what
  hid it last time.
- **Streaming limit.** A payload past `max_bytes` is rejected with the backend never seeing a write
  (§7.2).
- **Serve gate.** A stored `text/html` asset is served `attachment`, never `inline` (I6). An SVG is
  rejected at the accept gate.
- **Signing.** The five cases in §9.2, plus an assertion that verification uses `compare_digest`, plus
  the bucketing assertion from §9.1.
- **Sweeper.** Both passes, the grace window (an object written 5 minutes ago is *not* swept), and
  explicitly: **a row whose object is missing survives a sweep** (I3). Per §22.1 these use `freezegun`
  or an injected `now`, never `sleep`.
- **Transactionality.** A rolled-back `put` leaves no row; the orphaned object is reaped only after
  the grace period.
- **Route ordering.** `GET /api/files/usage` resolves to the usage handler, not to `{asset_id}`.
- **Boundaries.** `tests/core/test_boundaries.py` rejects a module importing
  `disp.core.files.backends.local`.
- **Reserved domain.** A fixture module declaring `domain="files"` is refused at discovery (§10).

**Coverage.** `src/disp/core/files/` warrants a **≥95%** gate, like `src/disp/core/auth/` — it is
security-sensitive code holding a signing key. That gate does not exist as machinery today: `./dev:94`
enforces only the global `--cov-fail-under=85`, and the auth ≥95 % figure in `CLAUDE.md` and
`TECHNICAL-SPEC.md` §22.2 is enforced by nothing.

**`vitest.config.ts:33-37`'s glob-keyed `coverage.thresholds` shape does not port** — that is a Vitest
feature and `coverage.py` has no per-path threshold equivalent. Implement it as additional
`coverage report --include=… --fail-under=95` invocations in `./dev test`, one per gated directory,
after the main run. Also confirm `concurrency = ["greenlet", "thread"]` (`pyproject.toml:73`) is still
set before believing any low number this produces.

## §15. Operations (`docs/operations.md` amendments)

### §15.1 Compose

Today the env var and the mount point differ: `DISP_PLANTS_MEDIA_ROOT: /data/media/plants`
(`docker-compose.yml:24`) inside a volume mounted at `media:/data/media` (`:26`), so the volume root
contains a `plants/` subdirectory. The change is **both** values, stated as a pair:

```yaml
DISP_FILES_ROOT: /data/files      # was DISP_PLANTS_MEDIA_ROOT: /data/media/plants
volumes:
  - media:/data/files             # was media:/data/media
```

**Keep the volume key named `media`** — renaming it orphans an existing deployment's data behind a name
nothing mounts any more. The pre-existing `plants/` subtree is then at `/data/files/plants` from the
container's point of view, which is what `disp-admin files adopt --root` must be pointed at during the
upgrade, before the new layout starts writing `plants/plant_photo/…` beside it.

`DISP_PLANTS_MEDIA_ROOT` and `DISP_PLANTS_MAX_IMAGE_BYTES` appear in five places that all need
updating: `.env.example:35-36`, `docker-compose.yml:24`, `src/disp/modules/plants/README.md`,
`CLAUDE.md` (plants gotchas), and `docs/milestones/client/M14-plants-screens.md:159`.

### §15.2 Backup

The existing `disp_media` tar cron (`docs/operations.md:105-106`) generalises unchanged — it tars the
volume root, not the plants subdirectory — and now covers every module's files rather than plants'. On
the `s3` backend, media backup becomes the provider's versioning/lifecycle policy and the cron is
dropped — say which one applies, explicitly, in the ops doc.

### §15.3 Restore

A database-only restore produces rows whose objects are absent. Requests then fail with
`404 core.files.missing_object`, which is a *visible* failure — an improvement on today's silent
`404 modules.plants.no_image`, which reads identically to "this plant simply has no photo" and makes
the gap easy to miss (`CLAUDE.md`, plants gotchas). §7's `open(session, ...)` signature exists to make
this distinction possible.

The sweeper MUST NOT interpret that state as garbage (I3). Consider it concretely: an operator
restores the database, the media volume fails to mount, the sweeper wakes at 04:30 and — under the
opposite rule — deletes every asset row in the platform, converting a recoverable mount error into
permanent metadata loss. Hence: objects without rows are garbage; rows without objects are an alert.

`disp-admin files verify` reports both directions (rows missing objects, objects missing rows) and
**deletes nothing**. It is the first thing to run after any restore.

## §16. Out of scope

Thumbnails and derived variants (the extension shape is a nullable `derived_from`/`variant` pair plus
a worker job — additive, no redesign, and the existing Procrastinate worker is the right home);
image resizing; content-addressed dedupe and refcounting; range requests; direct-to-browser S3
uploads; virus scanning; public/permanent URLs; per-user quota *enforcement* (`usage()` reports;
nothing blocks on it yet, and no error code is registered for it — §7).

**EXIF stripping — decided, not omitted.** Phone photos carry GPS coordinates, and §9.3 explains why
this milestone sharpens the exposure. It is still out of scope for v1, for two reasons:

1. **It would break §7.2's guarantee.** Stripping requires decoding the whole image, so peak memory
   would become "one chunk, except for images", where §7.2's whole point is that the bound holds for
   every type and every size. §7.2 is the section that fixes one of the three bugs §1 exists to fix.
2. **The threat model is 1–20 invite-only trusted users** (`TECHNICAL-SPEC.md` §1.3). The realistic
   exposure is a link forwarded to someone you know, not a scraper.

It is cleanly deferrable in a way most decisions here are not: assets are immutable and `sha256` is
computed over stored bytes, so adding a strip step later applies to new uploads only — no backfill, no
redesign. When it lands it needs Pillow, and hashing must move after the strip so `sha256`/`byte_size`
keep describing what is actually stored.

## §17. Backbone spec amendments

This milestone extends seven normative lists in `TECHNICAL-SPEC.md`. These edits are part of it:

| Section | Edit |
|---|---|
| §5.2 variable registry | 14 `DISP_FILES_*` rows; §5.4 requires `.env.example` list every variable |
| §8.4 `Platform` | add `files: FileStore` — the dataclass in that section is normative |
| §17.2 status codes | no rows for `413`, `415`, `302`, `304`; `plants` already exceeded the table with 413/415 |
| §17.7 OpenAPI | the tag list is closed (`domain`, `auth`, `dashboard`, `settings`, `health`) — add `files` |
| §21 security | signed URLs are HMAC-verified capabilities (S17); no key component derives from client input, I4 (S18); only positively-identified types render inline, I6 (S19) |
| §22.1 infrastructure | MinIO testcontainer; note it is localhost, not outbound I/O |
| §22.2 coverage | add `src/disp/core/files/` ≥ 95 %, and give the existing auth gate real machinery (§14) |
| Appendix A | 7 `core.files.*` codes (§7) |

`TECHNICAL-SPEC-WEB.md` §7.3 gains one row: `403 core.files.url_expired` → invalidate the parent query
and re-mint, per §13.

## Dependencies

`M21` (error code namespace) — codes here assume the three-segment shape.

Core otherwise: `Settings` (M1), `core` models and Alembic branch (M2, M5), auth dependencies (M6),
scheduler for the sweeper (M7), registry core-builtin registration (M10). Phase 2 depends on the
shipped `plants` module; phase 3 on the web client through `M11`.

`M20`/learning depends on this milestone for source uploads, and on §7.1's text family in particular.

## Verification

- `./dev test` green with the new per-directory coverage gates; `./dev lint` clean.
- Backend conformance suite passes identically for `local` and `s3` (MinIO).
- **Run the built image, don't just build it** — `docker compose up`, upload a photo, load its signed
  URL in a browser with no session, confirm the bytes arrive and that the URL 403s after `exp`. Both
  of this repo's Docker bugs were found by running the image, never by building it (`CLAUDE.md`).
- **Confirm a plant photo actually renders in the browser**, which it does not today (§1.3). This is
  the acceptance test for the milestone's user-visible half, and no unit test substitutes for it — the
  existing ones pass against the broken state.
- Flip `DISP_FILES_BACKEND` from `local` to `s3` against MinIO and confirm **no module or client code
  changes** — that is the milestone's actual thesis, and the only test of it is doing it.
- Run `disp-admin files adopt` against a real pre-migration media root and confirm every existing
  plant photo still renders.
