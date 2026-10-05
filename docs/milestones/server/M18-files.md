# M18 — core file service (v2: S3/R2 only)

**Status:** Implemented (v2), 2026-10-04. Supersedes v1 (local-disk backend, API-streamed signed
URLs) — see §14 for what v1 built and why it was replaced. v2 is normative for everything under
`src/disp/core/files/`; the code implements this document, not the other way round.

Verified:
- `./dev test` is green, including the ≥ 95 % gate on `src/disp/core/files/` (98 %).
- `./dev lint` is clean.
- In the built images (`docker-compose.yml` + `docker-compose.e2e.yml`), all three new migrations
  ran.
- The Playwright photo spec passes: upload, then on a fresh reload the `<img>` loads from a
  presigned MinIO link.
- Deleting a plant removed its object from the bucket within a second, and the old link then
  returned `404`.

**Not yet verified against real Cloudflare R2.** Every check above ran against MinIO, so the
first production deploy is the R2 acceptance test (§ Verification).

**Scope:** package `src/disp/core/files/` (`__init__.py`, `store.py`, `sigv4.py`, `sniff.py`,
`routes.py`, `sweep.py`, `backends/s3.py`), the `core.files` table (core Alembic revision
`0005_core_files`), `FileStore` on `Platform`, `DISP_FILES_*` settings, the `core.sweep_files`
scheduled job, `disp-admin files verify|sweep`. Ports `plants` and `learning` onto the v2 API.

**Covers:** no feature in `TECHNICAL-SPEC.md` — a capability the backbone spec never described. Like
`src/disp/modules/plants/TECHNICAL-SPEC.md`, this document is normative for itself. It amends the
backbone spec in the places listed in §13.

**Depends on `M21`** (error code namespace). Codes here are `core.files.*`.

---

## §1. What this is

One interface — `platform.files` — through which any module hands over bytes (an HTTP upload, a CLI
import, a worker job) and gets back a **file id**, and later exchanges that id for a **signed,
expiring link**. Modules store the id in their own table as a bare `uuid` column (no cross-schema FK)
and never learn where bytes live, which backend wrote them, or what the storage key is.

The only backend is **S3-compatible object storage**; the production deployment is **Cloudflare R2**.
R2 bills per GB-month stored and per operation (egress is free), so two properties are load-bearing
rather than nice-to-have:

1. **Nothing stale survives.** Deleting a file removes its object from the bucket within seconds of
   the deleting transaction committing (§8.2). Objects whose rows never committed are reaped by the
   sweeper (§8.3). Invariant **I7**.
2. **A rejected upload costs zero bucket operations.** All validation finishes before the first
   request to the bucket (§7.2).

## §2. Concepts and invariants

- **File** — one stored object plus its metadata row in `core.files`. Files are **immutable**: there
  is no overwrite. Replacing a plant photo creates a new file and deletes the old one.
- **Backend** — an implementation of the `StorageBackend` protocol (§6), registered under a stable
  **key** (`"s3"`). The key is persisted on every row (`core.files.backend`) and decides which backend
  reads and deletes that row's object. Writes always go to the backend named by
  `DISP_FILES_BACKEND`. Today exactly one backend exists; the key is the extension point for a second
  (another provider, a migration target) without a schema change.
- **Storage key** — the bucket-relative object key, derived entirely from platform-generated values
  (§5).
- **Owner** — the `core.users` row a file is billed to, for usage reporting. **The owner is not an
  ACL.** Whether a given user may see a given plant's photo is the `plants` module's judgement (plants
  are shareable via grants), made *before* it asks for a link (§9.3).
- **Link** — an S3 SigV4 presigned `GET` URL pointing directly at the bucket. A capability: anyone
  holding it gets the bytes until it expires, with no session.

Invariants, each pinned by a test:

- **I1** Bytes are written before the row referencing them is added to the caller's session.
- **I2** Bytes are never deleted before the transaction that deleted their row has committed.
  `delete()` only marks the row; the object is purged after commit (§8.2).
- **I3** No code path ever deletes a row *because its object is missing*. Objects without rows are
  garbage; rows without objects are an alert (`disp-admin files verify`).
- **I4** No part of a storage key ever derives from client input.
- **I5** The stored `content_type` is decided by what the bytes are, never by a declared
  `Content-Type` — except within the text family, which has no signature (§7.1).
- **I6** Only a positively-sniffed type is served `Content-Disposition: inline`; everything else is
  `attachment`. Enforced by signing `response-content-disposition` into every link (§9.2).
- **I7** Every object under `DISP_FILES_S3_PREFIX` is either referenced by a `core.files` row or is
  deleted by the sweeper within `files_orphan_grace_seconds` + one sweep interval.

## §3. Configuration

Core `Settings` (`src/disp/core/config.py`, env prefix `DISP_`). `model_config` is
`extra="forbid"` with `env_file=".env"`, so every variable is a declared field — and **a leftover v1
key in `.env` (`DISP_FILES_ROOT`, …) refuses to boot**. `docs/operations.md` carries the upgrade note.

| Field | Env | Default | Notes |
|---|---|---|---|
| `files_backend` | `DISP_FILES_BACKEND` | `s3` | `Literal["s3"]`; the backend new writes go to |
| `files_s3_bucket` | `DISP_FILES_S3_BUCKET` | `""` | **required** |
| `files_s3_endpoint_url` | `DISP_FILES_S3_ENDPOINT_URL` | `None` | what the server talks to. R2: `https://<account>.r2.cloudflarestorage.com`; unset = AWS |
| `files_s3_public_endpoint_url` | `DISP_FILES_S3_PUBLIC_ENDPOINT_URL` | `None` | what links point at; defaults to `files_s3_endpoint_url` (§9.2) |
| `files_s3_region` | `DISP_FILES_S3_REGION` | `auto` | R2 accepts `auto`; MinIO/AWS want a real region |
| `files_s3_access_key_id` | `DISP_FILES_S3_ACCESS_KEY_ID` | `SecretStr("")` | **required** |
| `files_s3_secret_access_key` | `DISP_FILES_S3_SECRET_ACCESS_KEY` | `SecretStr("")` | **required** |
| `files_s3_prefix` | `DISP_FILES_S3_PREFIX` | `""` | key prefix inside the bucket; the sweeper only ever lists and deletes under it |
| `files_s3_force_path_style` | `DISP_FILES_S3_FORCE_PATH_STYLE` | `true` | MinIO requires it; R2 accepts it |
| `files_max_bytes` | `DISP_FILES_MAX_BYTES` | `104_857_600` (100 MiB) | hard ceiling; an `AcceptSpec` may be stricter, never looser |
| `files_default_link_ttl_seconds` | `DISP_FILES_DEFAULT_LINK_TTL_SECONDS` | `3600` | `ge=60, le=604800`; used when `put()` gets no `link_ttl` |
| `files_orphan_grace_seconds` | `DISP_FILES_ORPHAN_GRACE_SECONDS` | `3600` | §8.3 pass B |
| `files_sweep_cron` | `DISP_FILES_SWEEP_CRON` | `17 * * * *` | hourly; plain `str` |

A `model_validator(mode="after")` rejects an empty bucket or empty credentials at startup. A
deployment with no storage must refuse to boot rather than fail on the first upload.

**There is no local backend and no media volume.** Development, the test suite and the e2e stack run
**MinIO** (`docker-compose.test.yml`, a testcontainer, `docker-compose.e2e.yml` respectively); only
production talks to R2. The image is **`pgsty/minio`**, pinned to a release tag (one `MINIO_IMAGE` value,
repeated in `tests/conftest.py` and both compose files). Upstream stopped publishing community
images: `minio/minio` on Docker Hub and `quay.io/minio/minio` both refuse pulls as of 2026-10.
`pgsty/minio` is a maintained drop-in fork with the same entrypoint and the same `server /data`
command. A dev environment must never point at the production bucket: the sweeper
deletes every object under the prefix that has no row *in its own database* (§8.3 pass B).

## §4. Data model — `core.files`

```sql
CREATE TABLE core.files (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id     UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
    domain            TEXT        NOT NULL,
    purpose           TEXT        NOT NULL,
    name              TEXT        NOT NULL,
    content_type      TEXT        NOT NULL,
    byte_size         BIGINT      NOT NULL,
    sha256            TEXT        NOT NULL,
    backend           TEXT        NOT NULL,
    bucket            TEXT        NOT NULL,
    storage_key       TEXT        NOT NULL,
    link_ttl_seconds  INTEGER     NOT NULL,
    attributes        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at        TIMESTAMPTZ,
    CONSTRAINT ck_files_domain    CHECK (domain ~ '^[a-z][a-z0-9_]{1,31}$'),
    CONSTRAINT ck_files_purpose   CHECK (purpose ~ '^[a-z][a-z0-9_]{1,63}$'),
    CONSTRAINT ck_files_name      CHECK (length(name) BETWEEN 1 AND 255),
    CONSTRAINT ck_files_byte_size CHECK (byte_size > 0),
    CONSTRAINT ck_files_sha256    CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_files_link_ttl  CHECK (link_ttl_seconds BETWEEN 60 AND 604800)
);
CREATE UNIQUE INDEX uq_files_location ON core.files (backend, bucket, storage_key);
CREATE INDEX ix_files_owner  ON core.files (owner_user_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX ix_files_lookup ON core.files (domain, purpose)               WHERE deleted_at IS NULL;
CREATE INDEX ix_files_purge  ON core.files (deleted_at)                    WHERE deleted_at IS NOT NULL;
```

ORM class: `FileRecord` in `src/disp/core/models.py` (not `File` — too easily confused with the
`StoredFile` DTO and with Python file objects). Like v1's `Asset`, the ORM `id` has
`default=uuid.uuid4` as well as the server default: the id is baked into the storage key, and bytes
are written before the row exists (I1, §5).

Column notes:

- **`backend` holds a registry key, not a class path.** A Python path
  (`disp.core.files.backends.s3.S3Backend`) would couple every row to the current code layout; a
  class rename would orphan the whole table. `"s3"` is stable. `FileStore` maps keys to backend
  instances.
- **`bucket` is stored per row** so that changing `DISP_FILES_S3_BUCKET` sends *new* writes to the
  new bucket without breaking links to files already in the old one.
- **`name`** is the display/download name: the uploaded filename with path components stripped,
  control characters removed and length capped at 255; when the caller gives none (or it sanitises
  to empty), `file<ext>`. It is used only in `Content-Disposition`, never in a key (I4).
- **`link_ttl_seconds`** is the file's link lifetime ceiling (§9.1), resolved at `put()` time and
  stored. Changing `files_default_link_ttl_seconds` later does not retroactively change existing
  files.
- **`attributes`**, not `metadata` — `metadata` is reserved on SQLAlchemy's `DeclarativeBase`.
- `domain` is caller-supplied and core cannot verify it; it is a label and a scoping key (§7), not
  a security boundary. Modules are in-tree code reviewed together.
- `owner_user_id … ON DELETE CASCADE`: deleting a user drops their rows; their objects become
  orphans and pass B of the sweeper reaps them (§8.3). No undo — consistent with user deletion
  having none anywhere else.

The ORM model is **not** part of the module-facing surface (§11); modules get the `StoredFile` DTO.

## §5. Storage key layout

```
<prefix><domain>/<purpose>/<YYYY>/<MM>/<file_id><ext>
plants/plant_photo/2026/10/9c3f…-e21a.jpg
```

`<ext>` comes from core's content-type → extension table. No component derives from client input
(I4). `<file_id>` and the date shard are generated in Python before the first byte is written. The
key is a **stored** column, never recomputed, so a layout change affects new files only.

## §6. `StorageBackend` protocol and the S3 backend

```python
class StorageBackend(Protocol):
    name: str  # registry key, persisted into core.files.backend
    bucket: str  # the bucket new writes go to

    async def put(self, key: str, body: BinaryIO, *, size: int, content_type: str) -> None: ...
    async def delete(self, bucket: str, key: str) -> None: ...  # idempotent
    def iter_objects(
        self, prefix: str
    ) -> AsyncIterator[tuple[str, datetime]]: ...  # bucket = self.bucket
    def presign_get(
        self,
        bucket: str,
        key: str,
        *,
        ttl: int,
        now: datetime,
        content_type: str,
        content_disposition: str,
    ) -> tuple[str, datetime]: ...  # (url, expires_at); pure, no I/O
```

`S3Backend` (`backends/s3.py`):

- **I/O via `aioboto3`** (a required dependency). One client per operation, opened with
  `async with session.client("s3", …)`. A long-lived client binds to the event loop that created it,
  and this code runs in the API, the worker, the CLI (`asyncio.run` per command) and tests.
  botocore is configured with `request_checksum_calculation="when_required"` and
  `response_checksum_validation="when_required"`; newer botocore's default CRC checksums are not
  accepted by every S3-compatible store.
- **`put` is a single `PutObject`** with an explicit `ContentLength` and `ContentType`. No multipart:
  every accepted file is ≤ `files_max_bytes` (≤ 100 MiB by default, far under the 5 GiB single-PUT
  limit). That means **no incomplete multipart uploads**, which R2 bills as stored bytes until a
  lifecycle rule aborts them.
- **`delete`** is `DeleteObject`, which S3 answers `204` whether or not the key exists. It is
  therefore idempotent and safe under concurrent purges.
- **`iter_objects`** paginates `ListObjectsV2` under `files_s3_prefix`. Only the sweeper and
  `verify` call it. On R2 a list is a billed (Class A) operation, at about one per 1 000 keys per
  sweep, which is negligible against the free tier.
- **`presign_get`** delegates to `sigv4.py` (§9.2). It performs no network I/O and creates no
  client.
- Any boto/network failure during `put` becomes `503 core.files.storage_unavailable`. Failures in
  `delete`/`iter_objects` are logged by their callers (the purge and the sweeper), which retry later.

## §7. `FileStore` — the module-facing facade

Constructed once via `FileStore.from_settings(settings, session_maker=…)` in `create_app()`,
`worker.py` and the `disp-admin files` CLI, and hung on `Platform` as `files`. The request-scoped
dependency is `get_file_store(request)`.

```python
stored: StoredFile = await files.put(
    session,
    owner=user,  # CurrentUser or a UUID (worker context)
    domain="plants",
    purpose="plant_photo",
    source=upload,  # UploadFile | bytes | AsyncIterator[bytes]
    name=upload.filename,
    accept=ACCEPT_IMAGES,
    link_ttl=timedelta(days=7),  # optional; ceiling for every link to this file
    attributes={"origin": "web"},  # optional, module-defined
)
plant.image_file_id = stored.id

link: FileLink = await files.link(session, plant.image_file_id, domain="plants")
link.url, link.expires_at
```

| Method | Contract |
|---|---|
| `put(session, *, owner, domain, purpose, source, name=None, accept, link_ttl=None, attributes=None) -> StoredFile` | Streams + validates (§7.2), uploads, adds the row to `session`. Does **not** commit (I1). `link_ttl` outside 60 s … 7 d is a `ValueError` (a programming error, not a client error). |
| `get(session, file_id, *, domain) -> StoredFile \| None` | `None` for unknown, soft-deleted, or another domain's file. |
| `link(session, file_id, *, domain, max_ttl=None) -> FileLink` | `404 core.files.not_found` for unknown, deleted, or another domain's file. TTL = `min(row.link_ttl_seconds, max_ttl)` — a reader may shorten, never extend (§9.1). |
| `links(session, file_ids, *, domain, max_ttl=None) -> dict[UUID, FileLink]` | Batched `link` in **one query** for list endpoints. Missing/deleted/foreign ids are simply absent from the result (no error). |
| `delete(session, file_id, *, domain) -> None` | Marks `deleted_at` and schedules the post-commit purge (§8.2). Idempotent. Unknown/foreign ids are a no-op. |
| `usage(session, *, owner=None, domain=None) -> UsageSummary` | Row count and byte total by domain/purpose/owner. |

`domain` is required on every read and delete: a module can only see and remove its own domain's
files. Ownership is deliberately *not* checked by core (§2, §9.3).

**There is deliberately no server-side read-back** (v1's `open()` is gone). Its only caller was
`learning`, which uploaded a source and then immediately downloaded it again to extract its text.
Against a bucket that is a billed GET plus a network round trip for bytes the request already
holds. A module that needs the bytes server-side reads the upload itself, capped at its own size
limit (`await upload.read(max_bytes + 1)`), uses them, and passes the same `bytes` to `put()`.
`put()` still enforces every limit, so an over-sized read is rejected there with `413`. A future
module that must re-read a stored file later (e.g. a worker transcoding video) adds a
`read(session, file_id, *, domain)` method here first.

`StoredFile` (frozen dataclass): `id`, `domain`, `purpose`, `name`, `content_type`, `byte_size`,
`sha256`, `link_ttl_seconds`, `created_at`. `FileLink` (frozen dataclass): `url`, `expires_at`.

Errors (RFC 9457, `core.files.*`). Modules surface these directly and MUST NOT re-code them:

| Code | Status | Raised by |
|---|---|---|
| `core.files.empty_upload` | 400 | `put` |
| `core.files.too_large` | 413 | `put` |
| `core.files.unsupported_type` | 415 | `put` |
| `core.files.not_found` | 404 | `link` |
| `core.files.storage_unavailable` | 503 | `put` (bucket unreachable or erroring) |

v1's `missing_object`, `url_expired` and `forbidden` are gone: nothing serves bytes through the API
any more, so nothing can emit them. An expired link now fails at R2 with R2's own `403`, which never
reaches the client's problem-detail path (§12).

### §7.1 Accept specs and the two gates

```python
@dataclass(frozen=True)
class AcceptSpec:
    content_types: frozenset[str]
    max_bytes: int

ACCEPT_IMAGES    = AcceptSpec({"image/jpeg", "image/png", "image/webp", "image/gif"}, 5 MiB)
ACCEPT_DOCUMENTS = AcceptSpec({"application/pdf", "text/plain", "text/markdown",
                               "text/html", "application/x-subrip"}, 25 MiB)
ACCEPT_VIDEOS    = AcceptSpec({"video/mp4", "video/quicktime", "video/webm"}, 100 MiB)
```

`max_bytes` is clamped to `files_max_bytes`. A module picks from core's type table; it cannot invent
a type.

**Accept gate.** A type is either *sniffable* — identified from its magic bytes and rejected if the
bytes disagree (I5) — or in the *text family*, validated by a strict incremental UTF-8 decode. Sniff
table (`sniff.py`):

| Type | Signature |
|---|---|
| `image/jpeg` | `FF D8 FF` |
| `image/png` | `89 50 4E 47 0D 0A 1A 0A` |
| `image/gif` | `GIF87a` / `GIF89a` |
| `image/webp` | `RIFF????WEBP` |
| `application/pdf` | `%PDF-` |
| `video/quicktime` | `????ftypqt  ` (ISO-BMFF `ftyp` box, major brand `qt  `) |
| `video/mp4` | `????ftyp` + a major brand in an explicit MP4 video list (`isom`, `iso2`–`iso6`, `mp41`, `mp42`, `avc1`, `dash`, `mmp4`, `M4V `, `M4VH`, `M4VP`, `MSNV`, `f4v `) |
| `video/webm` | `1A 45 DF A3` (EBML) **and** a `webm` DocType within the first 64 bytes |

The ISO-BMFF and EBML containers are shared with formats that are *not* on the table: HEIC photos
(`ftyp` brand `heic`/`mif1`), M4A audio (`M4A `), and Matroska (EBML DocType `matroska`). Those
must not be labelled video, so the brand and DocType are checked explicitly. Anything else in those
containers sniffs as nothing and is rejected. The sniff head is the first 64 bytes of the stream.

SVG is on no table: it is unsniffable XML text.

**Serve gate (I6).** Only a sniffed type — images, PDF, video — gets `inline`. The text family is
always `attachment`. Links point at the bucket's origin rather than ours, so a stored HTML file
cannot become same-origin XSS even if it rendered. `attachment` remains as defence in depth, and
because a browser rendering a user's `.html` upload is never the intent.

### §7.2 Streaming, validation, then one upload

`put` consumes `source` in 64 KiB chunks and, in one pass:

1. sniffs the first chunk and decides the type (§7.1);
2. rejects on the first byte past `max_bytes` **without consuming the rest of the body**;
3. runs the UTF-8 decoder for the text family;
4. updates a `sha256`;
5. writes the chunk to a `SpooledTemporaryFile` (first 1 MiB in memory, the rest on local temp
   disk).

Only after the stream is fully validated is the spool rewound and sent as **one `PutObject`**
(§6). Peak memory is one chunk plus the 1 MiB spool. A rejected upload — empty, too large, wrong
type, bad UTF-8 — **never reaches the bucket**, so it costs no billed operation and leaves nothing
to sweep. A test asserts the backend's `put` is never called for an oversized payload. A status-code
assertion alone would pass against a buffer-everything implementation too.

## §8. Lifecycle

An object store and a database commit are not one transaction. The design picks which way each
failure falls, and then bounds how long the waste can live.

### §8.1 Create

Bytes first, row second, both before the caller commits (I1). If the caller rolls back, an object
with no row is left behind. Pass B of the sweeper reaps it after `files_orphan_grace_seconds`
(I7). The inverse — a row with no object — is what this ordering prevents.

### §8.2 Delete → purge after commit

`delete()` sets `deleted_at` and records the id in the session's `info`. On the first such call per
session it registers SQLAlchemy `after_commit` / `after_rollback` listeners, the same mechanism as
`core/events.py`'s `publish_after_commit`, but self-contained so it does not depend on an
`EventBus` being bound:

- **after_rollback** → forget the pending ids. Nothing is purged (I2).
- **after_commit** → `loop.create_task(files.purge(ids))`, tracked in a set so the task is not
  garbage-collected mid-flight.

`purge(ids)` opens a **fresh** session (`session_scope(session_maker)`), selects rows with
`id IN ids AND deleted_at IS NOT NULL`, and for each one deletes the object, then the row, and
commits. The fresh session is what makes it correct. It only acts on deletion marks that are
actually committed and visible, so it is a no-op if run against an uncommitted mark (for example a
test whose "commit" only released a SAVEPOINT). Object-then-row order means a crash in between
leaves a marked row whose object is already gone. The next purge or sweep finishes it, because
`DeleteObject` is idempotent. Any purge failure is logged (`files_purge_failed`) and left for the
sweeper.

**Shutdown waits for in-flight purges.** A purge task started by a commit just before shutdown
would otherwise be cancelled mid-delete. Its mark would survive, but the bytes would then stay
billed until the next hourly sweep. `FileStore.wait_for_purges()` awaits every tracked task:
- the API calls it in `create_app()`'s lifespan teardown, after the worker queue closes and before
  the engine is disposed;
- the worker calls it in `worker.py`'s `_run()` `finally`, because a job that deletes a file has
  the same post-commit hook.

Tests use the same method to await a purge deterministically instead of sleeping.

Result: in the normal case a deleted file's bytes leave R2 a moment after the request that deleted
it commits. There is **no undo window**: the platform's need is "no stale bytes", not
"recoverable deletes".

### §8.3 The sweeper — `core.sweep_files`

The name is `core.sweep_files` (manifest-key namespace: two segments, `KEY_RE`). Registration
follows v1: `sweep.register_task(scheduler)` is idempotent, and the cron is bound with
`scheduler.register_periodic("core.sweep_files", settings.files_sweep_cron)` in both `app.py`
and `worker.py`.

- **Pass A — marked rows.** Every row with `deleted_at IS NOT NULL`, regardless of age: delete
  object, delete row. This catches purges that failed or never started (process died between commit
  and task).
- **Pass B — orphan objects.** `iter_objects(prefix)` → keys with no row in `core.files` (deleted or
  not) **and** `last_modified < now − files_orphan_grace_seconds` → delete. The grace stops the
  sweeper racing an in-flight `put` whose transaction has not committed yet. Pass B only covers the
  *current* bucket. A bucket switched away from keeps its non-orphan objects (their rows still point
  at it) and is reconciled with `verify`.

**I3:** neither pass ever deletes a row because its object is missing. Logs `swept_rows`,
`swept_objects`, `skipped_in_grace`. Safe to run concurrently with itself and with purges.

### §8.4 Module obligations

A module that stores file ids MUST call `files.delete` whenever the referencing record goes away —
including when it **soft**-deletes that record. A soft-deleted plant keeps its row forever, so a
photo left attached to it would be billed forever. Concretely: `plants.delete_plant` deletes the
plant's photo; `learning.delete_course` deletes every source file in the course; replacing a file
deletes the old one.

## §9. Links

### §9.1 Expiry policy

- The **ceiling** is set when the file is created: `put(link_ttl=…)`, stored as
  `link_ttl_seconds`. The default is `files_default_link_ttl_seconds` (1 h). The allowed range is
  60 s … 604 800 s: SigV4 caps a presigned URL at **7 days**, so "a month" or "never" cannot be a
  link.
- A reader may **shorten** it per call (`max_ttl`), never extend it.
- Rationale: link lifetime is a property of the file's sensitivity, known when it is created. A
  resume uploaded with `link_ttl=1h` cannot be exposed for a week by some later read path that
  forgot.
- Because modules mint a fresh link every time they serialize a response, the 7-day cap does not
  limit in-app use. It only bounds how long a *forwarded* link works.

Guidance: plant photos `7 d`; resumes and identity documents `1 h` or less.

### §9.2 Presigning — `sigv4.py`

Links are AWS Signature V4 **query-string presigned `GET` URLs**, computed by core's own pure
function rather than botocore's `generate_presigned_url`:

```
GET <public_endpoint>/<bucket>/<key>        (path-style; virtual-hosted when force_path_style=false)
  ?X-Amz-Algorithm=AWS4-HMAC-SHA256
  &X-Amz-Credential=<access_key>/<YYYYMMDD>/<region>/s3/aws4_request
  &X-Amz-Date=<signing_time>
  &X-Amz-Expires=<ttl>
  &X-Amz-SignedHeaders=host
  &response-content-disposition=<inline|attachment; filename*=UTF-8''…>
  &response-content-type=<content_type>
  &X-Amz-Signature=<hex>
```

**Why our own signer: bucketed signing time.** botocore signs with "now", so every mint produces a
different URL. Plants refetches its queries every 30 s, so each refetch would hand the `<img>` a new
`src` and re-download every thumbnail (a billed R2 read each time). `sigv4.py` signs at a
**bucketed** time:

```
g            = clamp(ttl // 10, 1, 3600)      # stability window
signing_time = floor(now / g) * g
expires_at   = signing_time + ttl             # X-Amz-Expires = ttl
```

The URL is byte-identical for `g` seconds, so the browser cache hits. Its real remaining lifetime is
in `(ttl − g, ttl]`: it **never outlives the stated TTL** (a 1 h resume link lives 54–60 min), and
never drops below 90 % of it. A test asserts two mints inside one window are identical. Another
asserts that `expires_at − now ≤ ttl`.

The signer also signs the `response-content-type` and `response-content-disposition` overrides, so
the headers R2 serves are core's decision (I5, I6), not the uploader's.

**Public vs. internal endpoint.** The host is part of the signature. The URL must therefore name the
host the *browser* reaches, which is not always the one the server uses: in the e2e stack the API
reaches `http://minio:9000`, the browser `http://localhost:9000`. `files_s3_public_endpoint_url`
covers that. For R2 both are the same `https://<account>.r2.cloudflarestorage.com`.

Correctness is pinned by AWS's published known-answer vector for query-string auth (`examplebucket`,
`test.txt`, `20130524T000000Z`, 86 400 s →
`aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404`), and end to end by fetching a
real presigned URL from MinIO in the test suite, which verifies signatures exactly as R2 does.

### §9.3 Where authorization happens

In the module, before asking for a link. `plants.get_plant` authorizes `read` on the plant, then
asks `files.links(...)` for its photo. Core checks only that the file exists, is not deleted, and
belongs to the calling domain. Core never learns what a plant is; `plants` never learns what a
storage key or bucket is.

### §9.4 What a link is and is not

It is a capability, exactly like S3 presigning, because it *is* S3 presigning. Mitigations: per-file
TTL ceilings (§9.1), and purge-on-delete (§8.2). Once a file is deleted, any link to it starts
failing as soon as the purge runs, not when the link expires.

> **Forwarding a link discloses the file's EXIF, including GPS**, for as long as the link lives.
> Stripping is out of scope (§15); the 7-day ceiling on plant photos is the bound.

The web client needs the bucket's origin in its CSP (`img-src`, `media-src`). See §12.

## §10. HTTP API — `/api/files`

Mounted in `create_app()`, tag `files`. `files` is a reserved module domain
(`registry.RESERVED_DOMAINS`), so no module can mount over it.

- **`GET /api/files/usage`** — admin only (`operation_id` `files_usage`); totals by domain, purpose,
  owner.

That is the whole router. v1's `GET /api/files/{id}` (signed-query or bearer, streamed) is removed:
bytes are served by the bucket. There is still no generic `POST /api/files`. Uploads go through the
owning module's route, so authorization and attaching the file to its parent record happen in one
transaction.

## §11. Module contract and boundaries

Public surface of `disp.core.files`: `FileStore`, `StoredFile`, `FileLink`, `AcceptSpec`,
`ACCEPT_IMAGES`, `ACCEPT_DOCUMENTS`, `ACCEPT_VIDEOS`, `UsageSummary`, `get_file_store`.
`tests/core/test_boundaries.py`'s `ALLOWED_FILES_NAMES` pins exactly that list. Submodules
(`backends.*`, `sigv4`, `sweep`, `store`) are off-limits to modules.

Ported modules:

- **plants** — column `plant.image_file_id` (was `image_asset_id`; plants revision
  `0003_plants_image_file` renames it and nulls existing values — v2 started with an empty file
  table). Photos are uploaded with `link_ttl=7 d`. `PlantOut.image_url` is the presigned link,
  fetched in one `links()` call per response. `GET /api/plants/{id}/image` is a `302` to it.
  `delete_plant` deletes the photo. See `src/disp/modules/plants/TECHNICAL-SPEC.md`.
- **learning** — column `source.file_id` (was `asset_id`; learning revision renames it and nulls
  existing values). `delete_source` deletes its file; `delete_course` deletes every source file of
  the course. See `src/disp/modules/learning/TECHNICAL-SPEC.md`.

## §12. Web client

- `clients/web/security-headers.conf`: `img-src 'self' data: https://*.r2.cloudflarestorage.com` and
  `media-src 'self' https://*.r2.cloudflarestorage.com`. Links are cross-origin now, and the wildcard
  covers both path-style and virtual-hosted R2 hosts. **Changing provider means editing this line.**
  Dev (`pnpm dev`) and e2e (`pnpm preview`) serve no CSP, so MinIO on `localhost:9000` needs no entry.
- `<img onError>` still cannot see an HTTP status. `PlantThumbnail.tsx` keeps the flow
  invalidate parent query → retry once (a fresh link) → `Sprout` placeholder.
- The `core.files.url_expired` branch in `usePlantMutations.ts` is removed. The code no longer
  exists, and an expired link never surfaced through a mutation anyway.
- No CORS rule is needed on the bucket: `<img>`/`<video>` without `crossorigin` do not require one.

## §13. Backbone spec amendments

| Document | Edit |
|---|---|
| `TECHNICAL-SPEC.md` §5.2 | the `DISP_FILES_*` rows of §3 |
| `TECHNICAL-SPEC.md` §8.4 | `Platform.files: FileStore` (unchanged from v1) |
| `TECHNICAL-SPEC.md` §17.7 | `files` tag (unchanged from v1) |
| `TECHNICAL-SPEC.md` §21 | S17: links are SigV4 presigned capabilities, ≤ 7 d, per-file ceiling; S18: I4; S19: I6 |
| `TECHNICAL-SPEC.md` §22.1 | MinIO testcontainer (localhost, not outbound I/O) |
| `TECHNICAL-SPEC.md` App. A | the five `core.files.*` codes of §7 |
| `TECHNICAL-SPEC-WEB.md` §7.3 | `url_expired` row removed; the `<img onError>` retry stays |

## §14. History — v1 and why it was replaced

v1 (commit `5b1bdc8`) shipped a **local-disk** backend (`backends/local.py` on a `media` volume),
an HMAC-signed `/api/files/{id}?exp&sig` route that streamed bytes through the API, soft-delete with
a 24 h undo grace, and `disp-admin files adopt` to backfill pre-M18 plant photos. Its specified S3
backend was never built: `FileStore.from_settings` raised for `files_backend="s3"`.

v2 replaces it because the deployment moved to Cloudflare R2 only:

- no volume, no media backup cron;
- bytes served by the bucket, not the API;
- immediate purge instead of a 24 h grace (storage is billed per GB);
- per-file link TTLs;
- video types.

v1's `core.assets` table was dropped without data migration (`0005_core_files`), by decision: the
installation started fresh. Also fixed in v2: two pre-existing leaks where soft-deleting a plant or a
learning course left its files stored forever (§8.4).

Kept from v1: the facade shape, immutability, I1/I3/I4/I5/I6, magic-byte sniffing and the text
family, the streaming size check, the bucketed-expiry idea (now applied to SigV4's signing time),
`verify`, and the reserved `files` domain.

## §15. Out of scope

Thumbnails/derived variants; image resizing or EXIF stripping (stripping would break §7.2's bounded
memory; the threat model is 1–20 trusted users); content-addressed dedupe; direct-to-browser uploads
(presigned `PUT`); virus scanning; public/permanent URLs; quota *enforcement* (`usage()` reports,
nothing blocks — no error code is registered for it); bucket versioning/backup (R2 does not version
objects; see `docs/operations.md`).

## Testing

- `tests/core/files/test_sigv4.py` — the AWS known-answer vector; identical URLs within a window;
  `expires_at − now ≤ ttl`; response overrides are signed (tampering one breaks the signature).
- `tests/core/files/test_store.py` (MinIO) — empty / oversized (backend `put` never called) /
  SVG / bad UTF-8 / declared-vs-sniffed type; TTL bounds; reader can shorten but not extend; domain
  scoping on `get`/`link`/`links`/`delete`; `links()` is one query.
- `tests/core/files/test_s3_backend.py` (MinIO) — put, idempotent delete, listing; **fetch a
  presigned URL over HTTP** → 200, right bytes, right `Content-Type`/`Content-Disposition`; an
  expired one → 403.
- `tests/core/files/test_purge.py` — delete + commit → object and row gone; delete + rollback →
  both intact; a failing backend leaves the marked row for the sweeper.
- `tests/core/files/test_sweep.py` — pass A; pass B honours the orphan grace and ignores keys
  outside the prefix; **a row whose object is missing survives** (I3).
- `tests/core/files/test_sniff.py` — every signature in §7.1.
- `tests/core/files/test_routes.py` — `GET /api/files/usage` is admin-only (403 otherwise), and
  no route serves bytes any more (v1's `GET /api/files/{id}` is gone).
- `tests/core/test_cli_admin.py` — `disp-admin files verify` reports both directions and deletes
  nothing; `disp-admin files sweep` purges marked rows.
- Modules — `delete_plant`, photo replacement, `delete_source` and `delete_course` each delete their
  files.
- Coverage: `src/disp/core/files/` ≥ 95 % (`./dev test`'s per-directory gate).

The MinIO container starts at `tests/conftest.py` import time next to Postgres, creates the bucket,
and sets `DISP_FILES_S3_*` as unconditional overrides.

## Verification

- `./dev up` (Postgres + MinIO), `./dev migrate`, `./dev test`, `./dev lint` green.
- Run the built images (`docker compose -f docker-compose.yml -f docker-compose.e2e.yml up`).
  Upload a plant photo, confirm it renders from a MinIO presigned URL on a fresh page load. Delete
  the plant, confirm the object is gone from the bucket within seconds.
- Against R2: upload, open the link with no session, confirm it 403s after expiry, delete, confirm
  the object is gone from the R2 dashboard. `disp-admin files verify` reports no differences.
