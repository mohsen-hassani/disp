# M23 — shopping module

**Status:** Not started (specification only — no code written).

**Scope:** new module `src/disp/modules/shopping/` (`__init__.py`, `manifest.py`, `config.py`,
`models.py`, `schemas.py`, `service/` as a package, `router.py`, `tiles.py`, `events.py`,
`translation.py`, `migrations/`), a `shopping` Postgres schema and Alembic branch with five tables,
`DISP_SHOPPING_*` module-owned settings, one settings panel, one dashboard tile, and one scheduled
job (`shopping.translate_pending`). Plus the three lines outside the module that every new module
needs: an `alembic.ini` section, one line in `tests/conftest.py`, one line in
`docker-compose.e2e.yml`.

**Covers:** nothing in `TECHNICAL-SPEC.md` — the backbone spec knows about `notes` (§18) and nothing
else. Like `src/disp/modules/plants/TECHNICAL-SPEC.md`, `M18-files.md`, `M19-llm.md` and
`M22-translation.md`, this document is therefore *normative for itself*: it is the source of truth
for anything under `src/disp/modules/shopping/`, not a summary of a spec section elsewhere.

**Depends on `M22`** (core translation service) — this module is its first consumer, and therefore
also the first real test of whether `platform.translation` is usable from a module without a `core/`
edit. **Depends on `M18`** (core files) for product images. **Depends on `M21`**: every error code
here is `modules.shopping.<error>`, the three-segment shape.

When implementation lands, distil the as-built reality into
`src/disp/modules/shopping/TECHNICAL-SPEC.md` (the way `plants` documents itself) and reduce this
file to a build log, the way `M00`–`M17` read today.

---

## §1. Why this exists

A shopping list is a deceptively good test of this platform, which is most of why it is worth
building. It is the first module that needs *all* of the following at once: a shared catalog with
per-resource ACLs on top of it, a background pipeline that spends real money, a settings panel whose
value is read by a worker rather than a request, an image on a `core.assets` row, and a read model
(analytics) whose correctness depends on columns chosen months earlier. Every one of those already
exists as a platform capability. None of them has been combined before.

Three concrete things it exercises that nothing else does:

1. **`core.translation` has no caller.** `M22` shipped `TranslationFacade`, wired it onto `Platform`
   (`src/disp/core/platform.py:27`) and into both `create_app()` and `worker.py:49`, and then
   stopped. `M22`'s own thesis — "point `DISP_TRANSLATION_BACKEND` at `fake` and back at `deepl` and
   confirm no caller code changes" — is untestable with zero callers. This module is that caller.
2. **No module has ever deferred an ad-hoc background job.** Both existing tasks are periodic:
   `notes.purge_deleted` and `plants.daily_check`, each registered in `register()` and bound to a
   cron by `Registry.wire()`. `SchedulerFacade.defer()` (`src/disp/core/scheduler.py:60-64`) exists
   and is used by nothing outside `core.notifier`. Work that must happen *because a user just did
   something*, rather than at 07:00, is a genuinely new shape for this codebase, and §5 is mostly
   about the trap it walks into.
3. **Nothing has needed a cross-user read of a settings panel.** `plants/reminders.py:33-57` reads
   one user's preferences at a time, inside a loop the job already had. Here the *union* of every
   user's language list determines what gets translated, and `SettingsStore` has no API for that
   (§6.2).

**The central design decision** is that **pending translation work is derived from the database, not
enqueued as a message.** A product's translations are considered current when a row exists for the
language *and* the row records the name it was translated from; anything else is pending, recomputed
from scratch on every sweep. Nothing is ever marked dirty, nothing is queued, and no outbox table
exists.

That decision is forced by a property of this codebase that is easy to miss. `publish_after_commit`
(`src/disp/core/events.py:93-102`) is not durable delivery — it registers an `after_commit` hook that
spawns a **fire-and-forget `asyncio` task** in the process that handled the request
(`events.py:77-87`). If that process is replaced mid-deploy, the event is gone, silently, with a
`_background_tasks` set as its only record. An architecture where "translate this product" is a
message is an architecture where a deploy at the wrong second permanently leaves a product
untranslated, with no way to notice and no way to find it again.

Deriving the work instead means a dropped message costs **latency and nothing else** — the next
sweep finds the same gap and fills it. It also means two features fall out for free rather than
being built: renaming a product re-translates it, and adding a language to the settings panel
back-fills the entire catalog. Both are described in §5.1, and neither has any code of its own.

## §2. Concepts and invariants

- **Catalog** — the set of `shopping.product` rows. **Global to the deployment**: a product has no
  owner and no ACL. Any authenticated user reads it and adds to it. This is a deliberate departure
  from `notes` and `plants`, argued in §9.1.
- **List** — a `shopping.shopping_list` row; what the user calls a buy session ("Party Saturday").
  Owned by a user, shareable, ACL'd exactly like a note. Lists are the *only* ACL'd resource in this
  module.
- **Item** — a `shopping.list_item` row: one product on one list, with an optional quantity and unit
  price, and a purchase state. The join table that makes a product belong to many sessions.
- **Translation row** — a `shopping.product_translation` row: one language's rendering of one
  product's name, plus the source name it was derived from. Not a cache — a durable record, because
  re-deriving it costs money.
- **Language union** — the set of language codes marked active by *any* user. The catalog is global,
  so its translations are too; visibility is filtered per user at read time (§6.1).
- **Base language** — English, implicitly. `product.name` is the base name and is never a
  translation row. There is no `EN` entry in anyone's language list, and a user who adds one gets it
  rejected (§6.1).

Invariants, each of which a test must pin:

- **S1** Product creation issues **no translation call on the request path**. A test asserts the
  fake backend recorded zero calls across `POST /api/shopping/products` and the quick-create branch
  of `POST /api/shopping/lists/{id}/items`.
- **S2** Pending work is derived from `(product.name, product_translation.source_name)` and the
  language union — never from a queue. Discarding every deferred job loses no work; the next
  periodic sweep produces identical results.
- **S3** Renaming a product invalidates exactly its own translations, and only by making
  `source_name` stale. No `UPDATE` and no `DELETE` touches `product_translation` on rename.
- **S4** A user sees only their own active languages. Deactivating a language hides its rows and
  **never deletes them**, so reactivating spends zero characters.
- **S5** "Update and Complete" is **one request**. Quantity/price and purchase state can never
  half-apply.
- **S6** `has_bought` and `bought_at` agree, enforced by a CHECK constraint rather than application
  discipline. Completing an already-bought item preserves the original `bought_at`.
- **S7** An item already marked bought cannot be moved to another list.
- **S8** Analytics never reports a price from a list the caller cannot read. The `readable_ids()`
  filter is applied **before** aggregation, not after.
- **S9** A product referenced by any `list_item` is soft-deleted only. Purchase history survives
  catalog cleanup.

> **S5 and S6 look like the same invariant and are not.** S5 is about the wire: two requests can
> half-apply on a flaky connection, leaving a price saved against an item the user believes they
> marked bought — in a supermarket, on mobile data, which is the entire deployment context for this
> screen. S6 is about the table: two columns encoding one fact will drift the first time a code path
> forgets one of them. Fixing either does nothing for the other.

## §3. Configuration

Module-owned `BaseSettings` in `src/disp/modules/shopping/config.py`, in the exact shape of
`plants/config.py:1-28` — a separate class with `env_prefix="DISP_SHOPPING_"` and `extra="ignore"`,
never fields on core `Settings` (which is `extra="forbid"`, and which
`tests/core/test_plugin_proof.py` asserts a new module cannot touch).

| Field | Env | Default | Notes |
|---|---|---|---|
| `currency` | `DISP_SHOPPING_CURRENCY` | `"EUR"` | ISO 4217, deployment-wide. Snapshotted onto each item at completion (§4.5) |
| `max_image_bytes` | `DISP_SHOPPING_MAX_IMAGE_BYTES` | `2 * 1024 * 1024` | Same value and reasoning as `plants` — an `AcceptSpec.max_bytes` tighter than the platform default |
| `translate_batch_size` | `DISP_SHOPPING_TRANSLATE_BATCH_SIZE` | `50` | Products per language per sweep. `M22` §2 is batch-first; one request per string is the expensive mistake |
| `translate_max_attempts` | `DISP_SHOPPING_TRANSLATE_MAX_ATTEMPTS` | `5` | After this many failures for one (product, language), stop retrying until the name changes |
| `translate_retry_minutes` | `DISP_SHOPPING_TRANSLATE_RETRY_MINUTES` | `60` | Backoff floor between attempts on a failed pair |
| `search_limit` | `DISP_SHOPPING_SEARCH_LIMIT` | `20` | Rows returned by the product typeahead |

> **Currency is deployment configuration, not a settings-panel field, and that is not a style
> preference.** A module gets exactly **one** HTTP-reachable settings panel:
> `Registry.settings_panel_for_domain()` (`src/disp/core/registry.py:245-250`) partitions on the
> panel key's *first* segment and returns the first match, so a second `shopping.*` panel would
> register successfully, appear in the dashboard manifest, and be permanently unreachable at
> `GET /api/settings/shopping`. `M22` §3 records the same defect biting `core.notifier`. One panel
> means one `scope`, and translation languages must be `scope="user"` (§6.1) — so a currency field
> in that panel would be per-user, which is incoherent for a list two people share. Config it is.
> **Do not "fix" this by adding a second panel.** Fixing `settings_panel_for_domain` is a core
> change and is not this milestone's job.

`translate_max_attempts` interacts with S2 in a way worth stating: a permanently failing pair (an
unsupported language code, say) would otherwise be retried forever, on every sweep, because pending
work is derived and a derivation has no memory. The attempt counter *is* that memory, and it lives
on the translation row rather than in a queue (§4.3).

## §4. Schema `shopping` — DDL

Own Postgres schema, own Alembic branch, hand-written `op.execute("""CREATE TABLE …""")` in the
style of `learning/migrations/versions/0001_learning_initial.py`, with `# --- §4.N ---` banner
comments mapping each block back to this document.

Foreign keys **within** the `shopping` schema are used freely. References to `core.users` and
`core.assets` are bare UUID columns with no FK, carrying the standing comment from
`plants/models.py:53`: *"No FK to core.users: modules must not create cross-schema foreign keys
(§6.1)."*

### §4.1 `category`

```sql
CREATE TABLE shopping.category (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_shopping_category_name ON shopping.category (lower(name));
```

Global, like the catalog it classifies. Categories are not translated: a category is an organising
device for the person filling the catalog, not vocabulary being practised, and translating them
would double the character bill for no product benefit. Say so rather than leaving it as an
apparent oversight.

### §4.2 `product`

```sql
CREATE TABLE shopping.product (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    name_normalized TEXT        NOT NULL,
    description     TEXT,
    category_id     UUID        REFERENCES shopping.category (id) ON DELETE SET NULL,
    image_asset_id  UUID,                    -- core.assets; no cross-schema FK
    unit            TEXT,                    -- "kg", "pack", … advisory, for comparable unit prices
    created_by      UUID        NOT NULL,    -- core.users; no cross-schema FK
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_shopping_product_name
    ON shopping.product (name_normalized) WHERE deleted_at IS NULL;
CREATE INDEX ix_shopping_product_search
    ON shopping.product (name_normalized) WHERE deleted_at IS NULL;
```

**`name_normalized` is the load-bearing column, and the unique index on it is the only thing
standing between this module and a catalog full of "Apple", "apple", " Apple " and "Apples".** The
quick-create-from-dropdown flow (§8.3) is *designed* to be fast and low-friction, which is exactly
the flow that manufactures near-duplicates; every duplicate then splits that product's price history
in two and makes §10's analytics quietly wrong. Normalisation is `strip()` → `casefold()` → collapse
internal whitespace. It is deliberately **not** stemming or plural-folding: "Apple" and "Apples" stay
distinct, because a normalisation aggressive enough to merge them will eventually merge two things
the user meant to keep apart, and there is no undo for a merge.

`unit` is advisory and optional. It exists because §10 reports unit prices, and a unit price is only
comparable across purchases when the user is consistent about what one unit *is*. Storing it on the
product rather than the item is what makes that consistency the default.

### §4.3 `product_translation`

```sql
CREATE TABLE shopping.product_translation (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id      UUID        NOT NULL REFERENCES shopping.product (id) ON DELETE CASCADE,
    lang            TEXT        NOT NULL,      -- normalised upper-case, e.g. "DE", "PT-BR"
    text            TEXT,                      -- NULL = attempted and failed
    source_name     TEXT        NOT NULL,      -- the product.name this was derived from
    backend         TEXT,                      -- TranslationBackend.name, for provenance
    attempts        INTEGER     NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    translated_at   TIMESTAMPTZ,
    CONSTRAINT uq_shopping_translation UNIQUE (product_id, lang),
    CONSTRAINT ck_shopping_translation_outcome
        CHECK (text IS NOT NULL OR last_attempt_at IS NOT NULL)
);
CREATE INDEX ix_shopping_translation_product ON shopping.product_translation (product_id);
```

Three columns carry the whole design and each deserves a sentence.

**`source_name` is what makes staleness derivable.** A row is current when
`source_name = product.name`; rename the product and every one of its rows becomes stale
simultaneously, with no `UPDATE`, no trigger, no dirty flag and no cascade (**S3**). This is the same
discipline `plants` applies to due/overdue state — *derived at read time, never stored* — applied to
a different kind of staleness. The alternative, a `stale BOOLEAN` set by the rename path, is one
forgotten call site away from a product whose German name is permanently the old one.

**`text IS NULL` means attempted-and-failed**, which is why the column is nullable and why the CHECK
constraint is phrased as it is: a row must carry either a result or evidence of an attempt. Without
this state a failed pair is indistinguishable from a never-tried pair, and §5.2's backoff has
nothing to back off from.

**Nothing here is deleted by a settings change.** Removing `RU` from every user's language list
leaves its rows in place, and re-adding it later is free (**S4**). Characters already spent are the
one resource this module cannot get back, so the table's default posture is to keep everything.

### §4.4 `shopping_list`

```sql
CREATE TABLE shopping.shopping_list (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    UUID        NOT NULL,     -- core.users; no cross-schema FK
    name        TEXT        NOT NULL,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at TIMESTAMPTZ,
    deleted_at  TIMESTAMPTZ
);
CREATE INDEX ix_shopping_list_owner
    ON shopping.shopping_list (owner_id, created_at DESC) WHERE deleted_at IS NULL;
```

Named `shopping_list`, not `list`. `LIST` is not a reserved word in Postgres, but
`shopping.list` reads as a type name in every ORM traceback and every `psql` session, and the
module's own domain prefix makes the qualified name no longer either way.

`archived_at` separates "this session is over" from "delete this". A finished shopping trip is
exactly the data §10 wants to keep, so the natural user gesture — clearing a completed list off the
main screen — must not be a delete.

### §4.5 `list_item`

```sql
CREATE TABLE shopping.list_item (
    id         UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    list_id    UUID           NOT NULL REFERENCES shopping.shopping_list (id) ON DELETE CASCADE,
    product_id UUID           NOT NULL REFERENCES shopping.product (id),
    quantity   NUMERIC(12,3),
    unit_price NUMERIC(12,2),
    currency   TEXT,                        -- snapshot; NULL until a price is set
    has_bought BOOLEAN        NOT NULL DEFAULT false,
    bought_at  TIMESTAMPTZ,
    bought_by  UUID,                        -- core.users; no cross-schema FK
    note       TEXT,
    position   INTEGER        NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT uq_shopping_list_item UNIQUE (list_id, product_id),
    CONSTRAINT ck_shopping_item_bought CHECK (has_bought = (bought_at IS NOT NULL)),
    CONSTRAINT ck_shopping_item_quantity CHECK (quantity IS NULL OR quantity > 0),
    CONSTRAINT ck_shopping_item_price CHECK (unit_price IS NULL OR unit_price >= 0)
);
CREATE INDEX ix_shopping_item_list ON shopping.list_item (list_id, position, created_at);
CREATE INDEX ix_shopping_item_purchases
    ON shopping.list_item (product_id, bought_at DESC) WHERE has_bought;
```

**The column is named `unit_price`, not `price`, and the name is the specification.** Price per unit
is what §10 needs and what makes two purchases comparable; the line total is
`unit_price × quantity`, computed at read time and never stored. A column called `price` would be
ambiguous at every call site forever, and the ambiguity would be discovered by an analytics chart
that is off by a factor of three.

`currency` is snapshotted rather than joined to `DISP_SHOPPING_CURRENCY`, because config is a
present-tense fact and a purchase is a past-tense one. A deployment that switches from EUR to CHF
must not silently redenominate two years of history.

`ck_shopping_item_bought` is **S6** as a constraint. It also decides a question the API would
otherwise have to answer by convention: there is no such thing as a bought item with no timestamp,
so §10 can index on `bought_at` and trust it.

`ix_shopping_item_purchases` is the analytics index and exists before analytics is written. Adding
it later means adding it to a table with the interesting amount of data in it.

## §5. The translation pipeline

One job name, `shopping.translate_pending`, registered inside `register()` with
`@platform.scheduler.task("shopping.translate_pending")` and declared in the manifest's
`scheduled_jobs` with a cron. It is reached two ways, and shipping both is the point:

| Trigger | Purpose | If it never fires |
|---|---|---|
| `platform.scheduler.defer(...)` from an event handler, after commit | Latency — translations appear seconds after a product is created | Nothing is lost; the sweep catches it |
| The manifest cron (`*/10 * * * *`) | Durability, and the only mechanism that is actually load-bearing | Translation stops entirely — this is the one to alert on |

The deferral path subscribes `ProductNameChanged` (a frozen dataclass in `events.py`, published via
`publish_after_commit` from both create and rename) and calls `platform.scheduler.defer` in the
handler. **It must be `publish_after_commit`, never a bare `defer()` inside the request
transaction** — a worker with `listen_notify=True` (`worker.py:100`) can pick the job up in
milliseconds, and a job that queries for a row its own transaction has not committed yet finds
nothing and exits successfully. That race is invisible in tests, which run inside a rolled-back
transaction where the worker never runs at all.

> **And when the after-commit handler is itself lost, nothing breaks** — which is the payoff for
> §1's central decision, and the reason this section can afford to be relaxed about a delivery
> mechanism that is explicitly not durable. Write a test that asserts it: run the sweep directly,
> with no event dispatched at all, and confirm the same translations land.

### §5.1 Deriving the work

One query per sweep, no bookkeeping table:

```
needed(product) = language_union                                      -- §6.2
current(product) = { row.lang : row.source_name = product.name
                              AND row.text IS NOT NULL }
retryable(product) = { row.lang : row.text IS NULL
                              AND row.attempts < translate_max_attempts
                              AND row.last_attempt_at < now() - translate_retry_minutes }

pending(product) = (needed − current) ∩ (never-attempted ∪ retryable ∪ stale)
```

Two behaviours fall out of this and are not implemented anywhere:

- **Adding a language back-fills the catalog.** A user adds `RU` to their panel; `language_union`
  grows; on the next sweep every product is pending for `RU`. There is no migration, no back-fill
  command, and no "translate everything" button — because there is nothing to trigger.
- **Renaming re-translates.** `source_name` stops matching, the row is stale, the sweep replaces it.
  The rename path itself does nothing but write the new name (**S3**).

Batch by language, not by product. One `platform.translation.translate([...], target_lang="DE")`
call carries up to `translate_batch_size` names; `M22` §5 makes `texts` a `Sequence[str]` with no
single-string convenience overload precisely to discourage the per-string loop. Results come back
in input order and `M22` guarantees the count (**T8**), so the zip back onto product ids is safe —
but assert the length anyway at the module boundary, because a corruption here attaches a fluent,
well-formed German word to the wrong product and looks like nothing at all.

### §5.2 Failure handling

Every `M22` error type reaches this job, and each gets a distinct response. Getting this table
wrong produces either a silent stall or a bill.

| Raised | Response |
|---|---|
| `TranslationNotConfigured` | Log once at INFO and return. A deployment with `DISP_TRANSLATION_ENABLED=false` is a supported configuration, not a fault — the module runs untranslated and the UI shows base names only |
| `TranslationQuotaExceeded` | **Abort the entire sweep immediately.** Do not try the next language. Record the attempt on the rows already dispatched. Log at WARNING with the backend name |
| `TranslationUnavailable` | Record the attempt (`attempts += 1`, `last_attempt_at = now()`), leave `text` NULL, continue to the next language |
| `TranslationRejected` | Same as above. A bad language code is a user-entered value (§6.1) and must not stall other languages |
| `TranslationInvalidResponse` | Same, plus log at ERROR — this one indicates a provider or backend defect, not a transient condition |
| `TranslationInputTooLarge` | A programming error: `translate_batch_size` names cannot exceed `translation_max_chars`. Log at ERROR and halve the batch for the retry rather than failing the pair |

**`TranslationQuotaExceeded` aborting the whole sweep is the one that matters.** Continuing after a
quota error means every remaining language issues a request that is guaranteed to fail, each one
incrementing `attempts` on rows that did nothing wrong, and each one burning a retry budget on a
condition that will not clear until the billing period does. `M22` §4.1 gave that error its own type
specifically so a caller could tell "an operator must act" apart from "try again later"; this is
the call site that was for.

### §5.3 What the job never does

It never writes `product.name`. It never deletes a translation row. It never calls the translation
facade for the base language. And it never translates `description`, `note`, or a category name —
only `product.name`, which is the vocabulary the user is practising. Each of these is a place where
"while we're here" would multiply the character bill by an amount nobody would notice until the
month ended.

## §6. Settings panel

### §6.1 The schema

`manifest.py` carries both the panel schema and `MANIFEST`, as `plants/manifest.py` does.

```python
class LanguageEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        default="",
        max_length=8,
        title="Language",
        description="A language code the provider accepts, e.g. DE, TR, RU, PT-BR.",
    )
    active: bool = Field(
        default=True,
        title="Active",
        description="Uncheck to hide this language without losing its translations.",
    )


class ShoppingSettingsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    translation_languages: list[LanguageEntry] = Field(
        default_factory=list,
        title="Translation languages",
        description="Product names are translated into these. English is the base language "
        "and is always shown.",
    )
```

**This renders in the existing generic settings screen with no client work at all**, which is worth
verifying rather than assuming: `fieldFor.tsx:90-105` accepts arrays whose items are objects (up to
`MAX_NESTING_DEPTH = 3`), and `ArrayWidget.tsx:19-80` supplies the Add/Remove rows. A list of
`{code, active}` is exactly the supported shape.

> **Every field in `LanguageEntry` MUST have a default, and `code` having `default=""` is not
> sloppiness.** `ArrayWidget.tsx:71` appends a literal `{}` when the user clicks Add, so a freshly
> added row has no keys at all. A required `code` would make the new empty row fail validation the
> instant it appears — an error message about a field the user has not reached yet. The server still
> rejects an empty code (below); the default exists so the *form* can hold a half-filled row.

Normalisation and validation, in a `model_validator(mode="after")`:

- Upper-case, `_` → `-` — the same normalisation `M22` §6 applies, so a user typing `pt_br` and a
  user typing `PT-BR` produce one language, not two.
- Reject `EN` and any `EN-*` with a clear message. English is the base language; a translation row
  for it would duplicate `product.name`, and DeepL deprecates bare `EN` as a target anyway
  (`M22` §6).
- Reject duplicates after normalisation.
- **Do not validate against a language table.** `M22` §6 argues this at length and the argument
  carries over unchanged: the table goes stale, it differs per provider, and a client-side rejection
  of a code the provider would have accepted is indistinguishable from the provider being wrong. An
  unknown code surfaces as `TranslationRejected` on that language only (§5.2).

Panel: `SettingsPanelSpec(key="shopping.preferences", scope="user")`. Per-user, because which
languages you are practising is personal — two people sharing a list can be learning different ones,
and both should get their own.

### §6.2 Reading the language union

The sweeper needs every user's list, and `SettingsStore` cannot produce it: `get_all`
(`src/disp/core/settings_store.py:99-113`) takes a single `user_id` and there is no cross-user
accessor. The two options are an N+1 over `core.users` or one query against `core.settings`.

Take the single query. `disp.core.models.Setting` is importable by a module —
`tests/core/test_boundaries.py` restricts `disp.core.db`, `disp.core.auth`, `disp.core.app` and
cross-module imports, and `core.models` is none of those; `notes/service.py:15` already imports
`User` this way for its share-by-email lookup, with the reasoning recorded in `M13`.

```sql
SELECT value_json FROM core.settings
WHERE module_domain = 'shopping' AND key = 'preferences.translation_languages';
```

The key shape is not arbitrary and is worth pinning: `update_domain_settings` writes
`f"{prefix}.{field_name}"` where `prefix` is the panel key minus its domain
(`settings_store.py:172-175`), so panel `shopping.preferences` + field `translation_languages`
gives `preferences.translation_languages`. A test MUST assert this exact key round-trips through
`PUT /api/settings/shopping`, because it is a string constructed in two places that would otherwise
drift apart in silence.

> **This read bypasses the store's decryption path, so `translation_languages` must never become a
> secret field.** Marking it `x-secret` would move the value into `value_encrypted` and leave
> `value_json` NULL, and the sweep would conclude that nobody wants any languages — no error, no log
> line, just translation quietly stopping. Pin it with a test asserting
> `_field_is_secret(ShoppingSettingsSchema.model_fields["translation_languages"])` is false, and
> say in a comment why that apparently pointless assertion exists.

Rows that fail to parse are skipped with a WARNING, not fatal — the same defensive posture
`plants/reminders.py:52-57` takes, and for the same reason: one hand-edited settings row must not
abort the sweep for everyone.

## §7. Manifest

```python
MANIFEST = ModuleManifest(
    domain="shopping",
    name="Shopping",
    version="1.0.0",
    description="Shopping lists with a shared product catalogue and translated product names.",
    tiles=(
        TileSpec(
            key="shopping.open_lists",
            title="Shopping",
            description="Lists with items still to buy.",
            size=TileSize.MEDIUM,
            refresh_seconds=120,
            order=30,
            nav=TileNavSpec(...),
        ),
    ),
    client_nav=ClientNavSpec(
        label="Shopping",
        icon="shopping-cart",              # kebab-case lucide name (M17)
        order=30,
        routes=("", "lists/new", "lists/{list_id}", "products", "products/{product_id}",
                "insights"),
    ),
    settings_panels=(SettingsPanelSpec(key="shopping.preferences", ..., scope="user"),),
    scheduled_jobs=(
        ScheduledJobSpec(
            name="shopping.translate_pending",
            cron="*/10 * * * *",
            description="Translate product names into every active language.",
        ),
    ),
)
```

The tile lists lists (sic) with unbought items and a remaining count, derived from
`readable_ids(ctx.session, user_id=ctx.user.id, resource_type="shopping.list")` — the same shape as
`notes/tiles.py:35`. Counts are computed at render time and never stored, matching the tile contract
in `plants/tiles.py`.

No `notification_types`. A "list shared with you" push is an obvious future addition and is
deliberately absent: it needs a delivery preference, a copy decision, and a notification type key
that becomes API surface the moment it ships. Declaring only what is actually wired is the
convention `learning/manifest.py:3-7` records.

## §8. HTTP API

Mounted at `/api/shopping`, tagged `shopping`, by core wiring — the module returns a bare
`APIRouter()` from `api_router()` with no prefix of its own.

**Route declaration order is mandatory, not stylistic.** Every literal segment — `/lists`,
`/products`, `/categories`, `/analytics` — MUST be declared before any sibling `/{...}` route, with
the warning comment `plants/router.py:40-42` carries verbatim. FastAPI matches in declaration order,
and a `/{product_id}` declared first swallows `/products` and fails UUID parsing with a 422 that
looks nothing like a routing bug.

| Method | Path | Operation id |
|---|---|---|
| GET | `/products` | `shopping_products_list` |
| POST | `/products` | `shopping_products_create` |
| GET | `/products/{product_id}` | `shopping_products_get` |
| PATCH | `/products/{product_id}` | `shopping_products_update` |
| DELETE | `/products/{product_id}` | `shopping_products_delete` |
| PUT | `/products/{product_id}/image` | `shopping_products_set_image` |
| DELETE | `/products/{product_id}/image` | `shopping_products_clear_image` |
| GET | `/categories` | `shopping_categories_list` |
| POST | `/categories` | `shopping_categories_create` |
| PATCH | `/categories/{category_id}` | `shopping_categories_update` |
| DELETE | `/categories/{category_id}` | `shopping_categories_delete` |
| GET | `/lists` | `shopping_lists_list` |
| POST | `/lists` | `shopping_lists_create` |
| GET | `/lists/{list_id}` | `shopping_lists_get` |
| PATCH | `/lists/{list_id}` | `shopping_lists_update` |
| DELETE | `/lists/{list_id}` | `shopping_lists_delete` |
| GET | `/lists/{list_id}/shares` | `shopping_lists_shares` |
| POST | `/lists/{list_id}/share` | `shopping_lists_share` |
| DELETE | `/lists/{list_id}/share/{user_id}` | `shopping_lists_unshare` |
| POST | `/lists/{list_id}/items` | `shopping_items_add` |
| GET | `/lists/{list_id}/items/{item_id}` | `shopping_items_get` |
| PATCH | `/lists/{list_id}/items/{item_id}` | `shopping_items_update` |
| POST | `/lists/{list_id}/items/{item_id}/move` | `shopping_items_move` |
| DELETE | `/lists/{list_id}/items/{item_id}` | `shopping_items_delete` |
| GET | `/analytics/price-history/{product_id}` | `shopping_analytics_price_history` |
| GET | `/analytics/purchases` | `shopping_analytics_purchases` |

`GET /products` query parameters: `q` (typeahead, matched against `name_normalized` with a prefix
then substring ranking), `category_id`, `cursor`, `limit`. Keyset pagination on `(created_at, id)`
via `disp.core.pagination`, exactly as `learning/service/courses.py:71-124` does it.

### §8.1 The three item buttons

| Button | Call | Body |
|---|---|---|
| Update | `PATCH .../items/{item_id}` | `{"quantity": …, "unit_price": …}` — `complete` omitted |
| Update and Complete | `PATCH .../items/{item_id}` | `{"quantity": …, "unit_price": …, "complete": true}` |
| Move | `POST .../items/{item_id}/move` | `{"target_list_id": "…"}` |

`complete` is a tri-state `bool | None`:

- **omitted / `null`** — leave purchase state exactly as it is. This is the "Update" button.
- **`true`** — mark bought. Set `bought_at = now()` and `bought_by = user.id` **only if not already
  bought**; a second completion preserves the first timestamp (**S6**), because that timestamp is
  what §10 reports and re-saving a price should not move a purchase to today.
- **`false`** — un-mark: clear `bought_at` and `bought_by`. Needed because the button is one tap and
  mis-taps happen in supermarkets.

**"Update and Complete" MUST be a single request** (**S5**). Implementing it as a PATCH followed by
a completion call means a dropped second request leaves a price recorded against an item the user
watched turn green. Setting `currency` from `DISP_SHOPPING_CURRENCY` happens in the same handler,
the first time a `unit_price` is written.

### §8.2 Move

`target_list_id` must be a list the caller can write (`require(..., "update", ...)` on both source
and target). Refuse when:

- the item is already bought → `409 modules.shopping.item_already_bought` (**S7**). A purchase
  happened during a session; relocating it rewrites the history §10 reads.
- the target already holds that product → `409 modules.shopping.item_exists`, from
  `uq_shopping_list_item`. Catch the `IntegrityError` and translate it rather than pre-checking —
  the pre-check races.
- the target *is* the source → `400 modules.shopping.same_list`.

### §8.3 Adding an item, and quick-create

```jsonc
POST /api/shopping/lists/{list_id}/items
{ "product_id": "…",  "quantity": 2, "unit_price": "1.49" }     // existing product
{ "new_product": { "name": "Sumac" }, "quantity": 1 }           // create and add, one round trip
```

Exactly one of `product_id` / `new_product` — a `model_validator` rejects both and neither. The
`new_product` branch resolves against `name_normalized` **first** and returns the existing product
if one matches, rather than 409-ing: the user's intent was "add sumac to this list", and a duplicate
name is this module's problem to absorb, not theirs to resolve. Only `name` is accepted here.
Description, category, unit and image are set later from the product screen — which is the whole
reason `name` is the only mandatory product field and the whole reason §5 is asynchronous.

`GET .../items/{item_id}` returns the product's translations **in the caller's own active
languages**, each either a `text` or an explicit `pending` marker. This is the language-practice
surface: opening an item to set its price is the moment the user sees "Apple / Apfel / Elma". A
language with no row yet MUST be reported as pending rather than omitted, so the client can say
"translating…" instead of silently showing fewer languages than the user configured (**S4**).

## §9. Authorization and sharing

### §9.1 Why the catalog has no ACL

`notes` and `plants` both own their rows per user. The catalog deliberately does not, and the
reasoning is worth recording because it looks like a missing feature:

A product is a *dictionary entry*, not a personal record. Two people in one household shopping from
one list must resolve "milk" to the same row, or the list holds two milks and §10 reports two
half-histories. Per-user catalogs would make every shared list a merge problem, and a per-product
ACL would make the typeahead a permissions query. Neither buys privacy worth having: the sensitive
data here is *what someone bought and for how much*, which lives on `list_item` and is protected by
the list's ACL.

So: `shopping.product` and `shopping.category` require authentication and nothing more.
`shopping.shopping_list` is ACL'd, and `list_item` inherits its list's ACL — an item is never
authorized against its product.

### §9.2 Lists

`RESOURCE_TYPE = "shopping.list"`. The pattern is `learning/service/courses.py`'s, verbatim:

- Create inserts the row, `flush()`es, then `grant(..., permission=Permission.OWNER,
  granted_by=user.id)` **in the same transaction** as the insert. A grant in a second transaction
  can leave an ownerless list if the process dies between them.
- List reads call `readable_ids(session, user_id=…, resource_type=RESOURCE_TYPE)` **once**, then a
  single `WHERE id IN (...)`. Never a per-row `can()`.
- `_authorize()` implements 404-vs-403: cannot read → 404; can read but not write → 403
  `core.acl.forbidden`. Never leak the existence of a list to someone with no grant.
- Sharing is by email, resolved through `select(User).where(func.lower(User.email) == …)` —
  `notes/service.py:205-224` is the reference implementation, including its self-share rejection.
  `permission` is `read` or `write`; `owner` is not grantable over HTTP.

Note that `readable_ids()` returns every resource with *any* grant, not only `read` grants
(`src/disp/core/auth/acl.py:163-174`). That is correct here — `write` and `owner` both outrank
`read` — but it means the returned set must not be reused as "lists the caller may edit".

## §10. Analytics

Two read endpoints. Both are ordinary authenticated reads, and both are governed by **S8**: the
`readable_ids()` filter on `shopping.list` is a `WHERE` clause inside the aggregate, never a
post-filter on the result. Aggregating first and filtering after leaks an average that encodes
someone else's prices.

**`GET /analytics/price-history/{product_id}`** — `?since=&until=`. One row per purchase of that
product in a readable list: `bought_at`, `unit_price`, `currency`, `quantity`, `list_id`,
`list_name`. Plus a summary: `min`, `max`, `latest`, and the change from first to latest. Rows with
`unit_price IS NULL` are excluded from the summary but returned in the series, flagged — "we bought
this and didn't record what it cost" is information.

**`GET /analytics/purchases`** — `?q=&product_id=&since=&until=&cursor=&limit=`. The "when did I buy
this and in which session" search, cursor-paginated on `(bought_at, id)` descending. `q` matches
`name_normalized`, so it finds products by base name; searching by *translated* name is deliberately
out of scope (§14).

Both group only across a single `currency`. Mixed-currency history is returned as separate series
rather than summed — converting requires an exchange rate as of a past date, which this module has
no business inventing.

## §11. Module contract and boundaries

Imports this module takes, all of which `tests/core/test_boundaries.py` already permits:

| From | Names |
|---|---|
| `disp.core.auth` | `CurrentUser`, `Permission`, `can`, `current_user`, `grant`, `list_grants`, `readable_ids`, `require`, `revoke` |
| `disp.core.db` | `get_session`, `session_scope`, `Base` |
| `disp.core.files` | `FileStore`, `AcceptSpec`, `ACCEPT_IMAGES`, `get_file_store` |
| `disp.core.translation` | `TranslationFacade` and the eight error types — via `platform.translation`, never constructed |
| `disp.core.models` | `Setting` (§6.2), `User` (§9.2) |
| `disp.core.contract`, `disp.core.errors`, `disp.core.events`, `disp.core.pagination` | as any module does |

No new allow-list entry is needed in `tests/core/test_boundaries.py`, and that is the headline: this
module is a plain consumer of surfaces `M18` and `M22` already sanctioned. If the implementation
finds itself wanting to widen one, stop — that is a signal the design drifted, not a formality.

### §11.1 Error codes

All three-segment `modules.shopping.*` per `M21`, validated by `ERROR_CODE_RE` in
`AppError.__init__`. Registered in the module's own spec, not `TECHNICAL-SPEC.md` Appendix A, which
registers `core.*` only.

| Code | Status | Raised when |
|---|---|---|
| `modules.shopping.not_found` | 404 | Any resource absent or not readable |
| `modules.shopping.product_exists` | 409 | `name_normalized` collides on an explicit create |
| `modules.shopping.item_exists` | 409 | `(list_id, product_id)` collides on add or move |
| `modules.shopping.item_already_bought` | 409 | Move attempted on a bought item (**S7**) |
| `modules.shopping.same_list` | 400 | Move target equals source |
| `modules.shopping.product_in_use` | 409 | Hard delete attempted on a referenced product (**S9**) |
| `modules.shopping.category_in_use` | 409 | Delete attempted on a category with products |
| `modules.shopping.cannot_share_with_self` | 400 | Share target is the caller |
| `modules.shopping.user_not_found` | 404 | Share email matches no user |
| `modules.shopping.invalid_language` | 422 | `EN`, a duplicate, or an empty code in the panel |

**A translation failure never produces an error code**, because it never reaches a client. The user
sees a pending language; the operator sees `core.translation_call` rows and a WARNING. A module MUST
NOT re-code a core error into its own namespace (`CLAUDE.md`), and "the translation provider is
down" is not a shopping-domain fact.

## §12. Testing

`tests/modules/test_shopping*.py`. **Test file basenames are globally unique across `tests/`** —
there is no `__init__.py` anywhere under `tests/`, so pytest derives module names from basenames
alone and a second `test_service.py` collides at collection time (`M22` §11 found this the hard
way). Use `test_shopping_products.py`, `test_shopping_lists.py`, `test_shopping_translation.py`,
`test_shopping_analytics.py`.

Cases that must exist, because they encode the invariants rather than the code:

1. **S1** — create a product with the fake translation backend installed; assert `backend.calls` is
   empty after the request returns. Then run the sweep and assert it is not.
2. **S2** — create three products, dispatch **no** event at all, run the periodic task directly, and
   assert all three are translated. This is the test that proves the message is optional.
3. **S3** — translate, then rename, then re-sweep; assert the new translation replaces the old and
   that no `product_translation` row was deleted in between (check `id` stability).
4. **S4** — two users with different active language sets read the same product; each sees only
   their own. Then deactivate a language and assert the row still exists in the database and no
   further translation call is made when it is reactivated.
5. **S5** — `PATCH` with `complete: true` in one request sets price and purchase state together;
   assert from a fresh session. A second `complete: true` leaves `bought_at` unchanged (**S6**).
6. **S6** — attempt a direct `UPDATE` setting `has_bought = true` with `bought_at` NULL; assert the
   database rejects it. Testing the constraint, not the service.
7. **S7** — move a bought item; assert 409 `modules.shopping.item_already_bought` and that the item
   did not move.
8. **S8** — user A has a list with prices, user B has none; B queries price history for the same
   product and gets an empty series, not A's numbers. Assert the SQL, not just the response, by
   also checking a shared-list case returns them.
9. **S9** — soft-delete a product that appears in a completed list; assert it vanishes from the
   typeahead and remains in `/analytics/purchases`.
10. **Quota abort** (§5.2) — a fake backend raising `TranslationQuotaExceeded` on the second
    language; assert the third language was never requested.
11. **Settings key round-trip** (§6.2) — `PUT /api/settings/shopping` then read
    `core.settings` directly and assert the key is exactly
    `preferences.translation_languages`.
12. **The panel is not secret** (§6.2) — assert `_field_is_secret` is false for
    `translation_languages`, with a comment explaining that the sweep reads `value_json` directly.
13. **Route order** — `GET /api/shopping/products` returns 200, not a 422 from UUID parsing. Trivial
    to write and the only thing that catches a reordering during a refactor.

No network, ever: the translation backend under test is `FakeTranslationBackend`
(`DISP_TRANSLATION_BACKEND=fake`), which stubs the transport and leaves `M22`'s real facade — usage
rows, budget checks, feature gates — in the path. That is `M22` §4.2's whole reason for putting the
seam at the network boundary rather than duck-typing the facade.

Coverage: the repo gate is ≥85% overall with ≥95% on `core/auth/`, `core/files/`, `core/llm/` and
`core/translation/`. This module gets **no** per-directory gate — it holds no credential and spends
money only through a facade that already has one. Adding a fifth `./dev` invocation for a module
would be the first time a *module* got one, and there is no reason here.

## §13. Operations (`docs/operations.md` amendments)

- `DISP_SHOPPING_*` joins the module-configuration section. None of it is secret; none of it needs
  rotation.
- **Translation cost is now real.** Until this module ships, `core.translation` has no callers and
  its character spend is zero. Point at `disp-admin translation usage` (`M22` §10) as the way to
  watch it, and note the shape of the spend: bursty at catalog-building time, near-zero afterwards,
  and one large spike whenever a user adds a language — which is a *catalog-sized* spike, not an
  item-sized one, and is the single most likely way to cross a free-tier ceiling.
- Add a monitoring note: if `shopping.translate_pending` stops running, nothing errors and nothing
  alerts — products simply stay untranslated. The check is "are there pending rows older than an
  hour", not "did a job fail".
- Product images live on the same `media:/data/files` volume as plant photos, on **both** `api` and
  `worker` (`M18`). No new volume, no new service, no image change.

## §14. Out of scope

Offline mutation queueing (the client blocks mutations offline; §M15 §8 records the risk honestly);
searching products by translated name (it needs the translation table in the search index and a
decision about which language wins a tie); a translation cache shared across modules (`M22` §13
already owns that decision); barcode scanning; recipes or meal plans that expand into items;
per-store price tracking; currency conversion; quantity units as a controlled vocabulary rather than
free text; splitting cost between users; push notifications of any kind (§7); a `shopping.*` CLI;
importing a catalog from a file.

> **Per-store prices deserve a decision rather than silent omission.** "How has the price changed"
> is a question whose honest answer is often "it didn't — you shopped somewhere else", and a
> `store` column on `list_item` would cost one nullable TEXT field today. It is out of scope because
> a store is really an entity (with a name people spell three ways), and adding it as free text now
> guarantees a migration later that has to deduplicate human-entered strings. Decide before the
> first analytics screen ships, not after there are two years of data.

## Dependencies

`M22` (translation facade, `platform.translation`), `M18` (`core.files`, `FileStore`, the media
volume on both `api` and `worker`), `M21` (three-segment error codes), `M17` (`client_nav` and
`TileNavSpec`), and the ordinary module contract from `M03`/`M05`/`M06`/`M07`/`M08`. Independent of
`M19` and `M20` — this module makes no LLM call.

Registration outside the module directory is three lines, per `docs/adding-a-module.md`: an
`[shopping]` section in `alembic.ini`, one `alembic --name shopping upgrade head` in
`tests/conftest.py`, one in `docker-compose.e2e.yml`'s `migrate` service. **Nothing under
`src/disp/core/` may change**, which `tests/core/test_plugin_proof.py` enforces by `git status`.

## Verification

- `./dev lint` clean — `mypy` runs `strict = true` over `disp.core.*`; module code is checked less
  strictly but the `Numeric` → `Decimal` boundaries are where a type error would actually bite.
- `./dev test` green, overall coverage still ≥85%.
- `./dev makemigration shopping "initial schema"` then `./dev migrate shopping`, then `./dev shell`
  and confirm all five tables, both CHECK constraints, and all four indexes exist.
- `DISP_MODULES=shopping` build of the app, then `git status --porcelain -- src/disp/core` is empty.
  That is the plugin-proof check run by hand, and it is the claim this module is making loudest.
- With `DISP_TRANSLATION_BACKEND=fake`: create a product, wait for one sweep, and confirm
  `product_translation` rows appear for every active language with `source_name` matching. Then
  rename the product and confirm the rows are replaced rather than duplicated.
- With `DISP_TRANSLATION_ENABLED=false`: create products, run the sweep, and confirm the app is
  entirely healthy — no errors, no retry storm, one INFO line, base names throughout. **A deployment
  that does not want translation must not notice this module has it.**
- Add a language to the settings panel with 40 products already in the catalog, run one sweep, and
  confirm the character spend in `core.translation_call` matches the catalog size — this is the
  spike §13 warns operators about, and seeing the number once is worth more than the paragraph.
- **Run the built image, don't just build it** — `docker compose up`, then exercise create → add to
  list → complete → analytics against the real stack. Both of this repo's Docker bugs were found by
  running the image, never by building it (`CLAUDE.md`).
- Point `DISP_TRANSLATION_BACKEND` at `fake` and back at `deepl` with no module change. `M22`'s
  thesis is provider substitutability and this module is the first thing in the repo that can
  actually test it.
