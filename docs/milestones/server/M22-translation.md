# M22 — core translation service

**Status:** Implemented. `src/disp/core/translation/` exists, `./dev lint` and `./dev test` are
green (432 passed, 91.15% overall) and the new `≥95%` per-directory gate reports **100%**. Seven
spec details were resolved or corrected during implementation and are recorded inline where they
matter — §4's subclass hooks (`_read_*`, not `_parse_*`, so **T8** cannot be forgotten by a new
backend), §9's "the boundary greps scan comments too", §10's `disp-admin translation usage`, §11's
unique-test-basename constraint, and §5's empty-batch short circuit. **Not yet done:** distilling
this document into `docs/translation.md` and reducing this file to a build log, per this section's
own instruction below; the live-key verification steps at the bottom, which need a real DeepL
account.

**Scope:** new package `src/disp/core/translation/` (`__init__.py`, `schema.py`, `errors.py`,
`facade.py`, `usage.py`, `backends/base.py`, `backends/deepl.py`, `backends/fake.py`), a
`core.translation_call` table + core Alembic revision, `TranslationFacade` on `Platform` as
`translation`, `DISP_TRANSLATION_*` settings, a sync `session_scope` mirror in `core/db.py` (the
first sync database surface in `src/`), and a fourth per-directory coverage gate in `./dev`.

**Covers:** nothing in `TECHNICAL-SPEC.md` — the backbone spec predates any notion of a translation
capability in this platform. Like `src/disp/modules/plants/TECHNICAL-SPEC.md`, `M18-files.md` and
`M19-llm.md`, this document is therefore *normative for itself*: it is the source of truth for
anything under `src/disp/core/translation/`, not a summary of a spec section elsewhere.

**Depends on `M21`** (error code namespace). The accounting codes here are `core.translation.*` —
the current three-segment shape, not a new fourth one.

When implementation lands, distil the as-built reality into `docs/translation.md` and reduce this
file to a build log, the way `M00`–`M17` read today.

---

## §1. Why this exists

Nothing in this repo can translate a string. `pyproject.toml` carries no translation SDK,
`core/config.py` has no field for a provider key, and no code path anywhere reaches a translation
API. Any module that wants translated output today has to invent the whole thing.

The tempting shortcut is `modules/<domain>/translate.py` — a module-owned client, the way
`plants/config.py` owns `DISP_PLANTS_*`. That shortcut is wrong here, and this repo has already
written the argument down twice in two different domains. `M18` §1: `plants` invented private media
storage because nothing shared existed, and the platform consequently acquired a bespoke backup
path, a bespoke sniffing table, and two chances to get path traversal wrong. `M19` §1: an LLM client
holds a credential, spends money per call, needs retry and timeout policy, needs usage accounting,
and needs a test double — every one of those a cross-cutting concern a second module would
reimplement or, more likely, copy.

A translation client is the same shape as the LLM client on every one of those axes, and adds one
the LLM client does not have: **providers are genuinely interchangeable**. There is no "Anthropic
publishes no embeddings endpoint" here. DeepL, Lara and LibreTranslate all translate text between
languages, and the difference between them is price, hosting model, and quality — deployment
concerns, not code concerns. That makes provider-swappability the *point* of this service rather
than a hedge.

Three problems this fixes on the way:

1. **No module may add a field to core `Settings`.** `src/disp/core/config.py` sets
   `extra="forbid"`, and `tests/core/test_plugin_proof.py` asserts that adding a module changes zero
   files under `src/disp/core/`. A module-owned provider key therefore has to live in a module-owned
   `BaseSettings` — which means the credential's lifecycle, rotation, and startup validation get
   invented once per module rather than once per platform.
2. **Nothing in this codebase can currently be tested against a translation provider.** The test
   suite is hermetic. §4.2's fake backend is the piece that makes a translation-dependent call site
   testable at all, and — unlike `M19` §9's `FakeLLM` — it stubs only the network, so the facade
   under test is the real one.
3. **Cost is invisible.** DeepL bills per character and its free tier is a hard 500 000-character
   monthly ceiling that returns `456` when crossed. §7's `core.translation_call` table means the
   first question anyone asks in production — *how close am I to the ceiling* — has an answer that
   does not require a provider dashboard.

**The central design decision** is that the sync and async surfaces are **one implementation with
two transports, not two implementations**. `httpx` ships `Client` and `AsyncClient` with identical
request/response objects, so a backend builds a request with a pure function, hands it to whichever
transport the caller asked for, and parses the response with another pure function. The alternative —
writing `translate()` and `translate_sync()` as two independent code paths — produces two subtly
different sets of headers, two error mappings, and a bug that reproduces on exactly one of them.

**A consequence worth stating up front:** the sync path needs to write a `core.translation_call` row
(**T5**), and `src/disp/core/db.py` is async-only. There is no sync SQLAlchemy session anywhere in
`src/` today. This milestone adds one (§7.1). That is a real addition to a core primitive and it is
not incidental — it is the price of a sync surface that is honest about its accounting.

## §2. Concepts and invariants

- **Backend** — one provider implementation (`deepl`, `fake`). Its `name` is persisted into every
  `core.translation_call` row, the way `StorageBackend.name` is persisted into `core.assets`
  (`M18` §6).
- **Facade** — `platform.translation`. The only surface a module may touch. Which provider, which
  base URL, and which retry policy sit behind it are deployment concerns a module cannot observe.
- **Feature** — a capability a backend either has or does not: `translate`, `detect`, `formality`.
  Declared on the backend as `supports`, and enforced by the backend raising (§4).
- **Batch** — one call carries a *list* of texts. The API is batch-first because every provider's
  is, and because one request per string is the expensive mistake.

Invariants, each of which a test must pin:

- **T1** A module cannot observe which backend is in use. `disp.core.translation`'s public surface
  names no vendor, and the string `deepl.com` appears in exactly one file.
- **T2** The sync and async surfaces are the same implementation modulo transport: for identical
  input they issue byte-identical HTTP requests and return equal results.
- **T3** The sync surface never creates, enters, or requires an event loop. `asyncio.run` appears
  nowhere under `src/disp/core/translation/`.
- **T4** A feature a backend does not support raises `TranslationNotSupported` **from the backend**,
  before any network request — and `backend.supports` agrees with what the backend actually raises.
- **T5** Every *dispatched* call writes exactly one `core.translation_call` row, including failed
  ones, committed before the exception propagates. `TranslationNotConfigured` writes none.
- **T6** No source text, no translated text, and no API key is ever written to a log at any level,
  including DEBUG. Log lines carry backend, operation, language pair, counts, latency and outcome —
  nothing else (§8).
- **T7** Input exceeding `translation_max_chars` raises `TranslationInputTooLarge` **before** any
  network request. The facade never silently truncates or splits a caller's input.
- **T8** `translate()` returns exactly as many strings as it was given, in the order it was given
  them. A backend returning a different count raises `TranslationInvalidResponse`.

> **T8 has no analogue in `M19`, and it is the most valuable invariant here.** A batch whose results
> come back misaligned by one produces output that is fluent, well-formed, and attached to the wrong
> record — a corruption with no visible symptom, which is the worst kind. Every provider's batch
> endpoint promises order preservation; none of them is worth trusting without the assertion.

## §3. Configuration

Added to core `Settings` (`src/disp/core/config.py`, env prefix `DISP_`), under a
`# M22: core translation service (src/disp/core/translation/).` banner beside the `M18`/`M19`
blocks. `model_config` sets `extra="forbid"`, so every one of these must exist as a field on the
class — an env var alone will not do.

| Field | Env | Default | Notes |
|---|---|---|---|
| `translation_enabled` | `DISP_TRANSLATION_ENABLED` | `false` | When false, the facade raises `TranslationNotConfigured` on every call and constructs no backend. Keeps a deployment that wants no translation from needing a key |
| `translation_backend` | `DISP_TRANSLATION_BACKEND` | `deepl` | `deepl` \| `fake` |
| `translation_api_key` | `DISP_TRANSLATION_API_KEY` | `SecretStr("")` | |
| `translation_base_url` | `DISP_TRANSLATION_BASE_URL` | `""` | Empty means "let the backend decide" — which for DeepL is not a constant (§4.1) |
| `translation_default_target_lang` | `DISP_TRANSLATION_DEFAULT_TARGET_LANG` | `""` | Optional deployment default for callers that do not name one. Empty means a caller MUST pass `target_lang` |
| `translation_timeout_seconds` | `DISP_TRANSLATION_TIMEOUT_SECONDS` | `30` | `ge=1, le=300`. Two orders of magnitude below `llm_timeout_seconds` — translation is a sub-second operation and a 600-second ceiling would hold a request open through an outage |
| `translation_max_retries` | `DISP_TRANSLATION_MAX_RETRIES` | `2` | Passed to the `httpx` transport, which retries connection failures only |
| `translation_max_chars` | `DISP_TRANSLATION_MAX_CHARS` | `120000` | Total characters across one batch. Below DeepL's own 128 KiB request ceiling, with headroom for JSON overhead |

`translation_backend` is a `Literal["deepl", "fake"]`, **not a free string**, so an unknown value
fails at settings validation rather than at first call — which is also why the backend factory can
end in an unguarded `return` rather than a `raise ValueError(f"unknown backend {…}")`. The literal
deliberately lists only what is implemented; adding a provider is one `Literal` member plus one file
under `backends/`, and nothing else (§4.3).

A `model_validator(mode="after")` MUST reject `translation_enabled=true` with an empty
`translation_api_key` **when the backend requires a credential**, in the provider-conditional shape
`_validate_embedding_configured` already uses (`config.py:129-140`) — the `fake` backend needs no
key, and a hermetic dev or test deployment must be able to set `DISP_TRANSLATION_ENABLED=true`
without inventing one. Failing at startup is the point: a deployment whose translation calls all
fail two minutes into a worker run is worse than one that refuses to boot.

> **Do not put the API key in the settings store.** It is a deployment secret, like
> `DISP_SETTINGS_KEY` and `DISP_LLM_API_KEY` — and putting it in `core.settings` would be circular,
> since the settings store needs `DISP_SETTINGS_KEY` to decrypt its own secret fields before it
> could produce this one.
>
> A `core.translation` settings *panel* is separately blocked by a mechanism worth knowing about:
> `Registry.settings_panel_for_domain()` (`registry.py:245`) matches on the panel key's **first**
> segment, so `core.notifier` already owns the entire `core` domain over HTTP. A second core panel
> would register, would appear in the dashboard manifest, and would be unreachable at
> `GET /api/settings/core`. Fixing that is not this milestone's job.

## §4. `TranslationBackend` — the provider interface

A structural `typing.Protocol`. Implementations do **not** subclass it, matching `StorageBackend`
(`files/store.py:31`) and `EmbeddingProvider` (`llm/embeddings.py`). There is no registry dict, no
entry points, and no plugin discovery — the set of backends is a closed `Literal` in `Settings`
(§3), because a translation provider is a deployment choice, not a third-party extension point.

```python
class Feature(StrEnum):
    TRANSLATE = "translate"
    DETECT = "detect"
    FORMALITY = "formality"


class TranslationBackend(Protocol):
    name: str  # "deepl" | "fake" — persisted into translation_call.backend
    supports: frozenset[Feature]

    async def translate(self, req: TranslateRequest) -> list[Translated]: ...
    async def detect(self, req: DetectRequest) -> list[Detected]: ...

    def translate_sync(self, req: TranslateRequest) -> list[Translated]: ...
    def detect_sync(self, req: DetectRequest) -> list[Detected]: ...

    async def aclose(self) -> None: ...
    def close(self) -> None: ...
```

**A backend that does not support a feature MUST raise `TranslationNotSupported` from the method
itself**, before any network request (**T4**). Declaring the gap in `supports` is not sufficient on
its own: `supports` is advisory metadata a caller may consult, and a caller that does not consult it
must still get a clear, typed refusal rather than a provider-shaped 400 or — worse — a plausible
wrong answer. A test MUST assert the two agree, in both directions: every feature absent from
`supports` raises, and every feature present does not.

The dual transport is not each backend's problem. `backends/base.py` also ships
`HTTPTranslationBackend`, a concrete base class (not a Protocol) that owns both an `httpx.Client`
and an `httpx.AsyncClient`, and the status-code-to-exception mapping. A subclass supplies **only
pure functions**:

```python
class HTTPTranslationBackend:
    # Subclass hooks — pure, no I/O.
    def _build_translate(self, req: TranslateRequest) -> HTTPCall: ...
    def _read_translate(self, payload: Any) -> list[Translated]: ...
    def _build_detect(self, req: DetectRequest) -> HTTPCall: ...
    def _read_detect(self, payload: Any) -> list[Detected]: ...

    # Concrete in the base — subclasses neither implement nor call these.
    def _parse_translate(self, payload: Any, req: TranslateRequest) -> list[Translated]: ...
    def _parse_detect(self, payload: Any, req: DetectRequest) -> list[Detected]: ...
```

`translate()` is `self._parse_translate(await self._send_async(self._build_translate(req)), req)`
and `translate_sync()` is `self._parse_translate(self._send_sync(self._build_translate(req)), req)`.
**This is what makes T2 structural rather than a matter of discipline** — the two paths call the
same builder and the same parser, and the only thing that differs is which `httpx` client the
`HTTPCall` is handed to. Writing the two methods independently would make T2 a promise; writing
them this way makes it a consequence.

> **Resolved during implementation: the parse step is split in two.** The subclass hook is
> `_read_translate(payload)` — provider-shape parsing only — and `_parse_translate(payload, req)` is
> **concrete in the base**, wrapping the hook with the item-count assertion. The original single
> `_parse_*` hook would have made **T8** something every new backend has to remember; this way a
> backend author cannot skip it, because they never write the method that would have skipped it.
> The same split applies to detect.

Both clients get an explicit `httpx.Timeout(settings.translation_timeout_seconds)` and a transport
with `retries=settings.translation_max_retries`, and both are closed. That is a deliberate
correction of `llm/embeddings.py`, where the `httpx.AsyncClient()` is constructed inline with
neither a timeout nor retries and is never closed — a leak that has not bitten anything yet only
because embeddings are rarely called.

> **The `httpx` transport's `retries=` retries connection failures, not HTTP status codes.** A 429
> or a 503 comes back as a response, not an exception, and is mapped to `TranslationUnavailable`
> without a retry. That is deliberate for a first pass: a retry loop over a per-character-billed API
> needs a budget, and §13 puts it out of scope explicitly rather than shipping an unbounded one.

### §4.1 DeepL backend — `backends/deepl.py`

**No `deepl` SDK.** The official package is a second HTTP stack whose principal value is exactly the
sync/async split this milestone is building anyway, and adding it would put a vendor name in the
dependency graph for no gain. Raw `httpx` against `POST /v2/translate`, which is already a
first-class dependency.

Four provider facts the implementer must not discover at runtime:

- **A free-tier key ends in `:fx` and MUST be sent to `api-free.deepl.com`; a pro key MUST go to
  `api.deepl.com`.** Crossing them returns a `403` whose message reads like a bad credential. When
  `translation_base_url` is empty, derive the host from the key suffix; when it is set, use it
  verbatim, because a self-hosted proxy is a legitimate reason to override. Hardcoding one host
  makes every free-tier deployment fail in the most misleading way available.
- **The auth header is `Authorization: DeepL-Auth-Key <key>`**, not `Bearer`.
- **`456` is quota-exceeded**, and it is the one 4xx an *operator* must act on rather than a caller —
  hence its own `TranslationQuotaExceeded` rather than being folded into `TranslationRejected`. A
  service that reports "bad request" when the month's character budget ran out sends whoever is
  debugging it to read code instead of a billing page.
- **DeepL has no standalone detect endpoint.** `detect()` is a translate call with `source_lang`
  omitted, reading back `detected_source_language` from each result. This is precisely the kind of
  provider shape the facade exists to hide (**T1**) — and it is why `detect()` is worth having on
  the interface at all rather than telling callers to "just translate and look at the field".

`supports = {TRANSLATE, DETECT, FORMALITY}`.

> Because detect is implemented as a translate call, a DeepL `detect()` **costs characters**. Record
> them in `char_count` like any other call (§7); reporting zero would make the usage table
> under-count against the provider's own meter, which is the one number it exists to reconcile with.

### §4.2 Fake backend — `backends/fake.py`

Selected by `DISP_TRANSLATION_BACKEND=fake` and exported from `disp.core.translation`, because
module tests need it.

```python
backend = FakeTranslationBackend(supports=frozenset({Feature.TRANSLATE, Feature.DETECT}))
backend.register("Hello", target_lang="de", result="Hallo")
backend.register_error("Boom", error=TranslationUnavailable("upstream down"))
```

**It is a fake *backend*, not a fake facade** — and that is a deliberate departure from `M19` §9's
`FakeLLM`, which duck-types the whole facade. Replacing the facade means a test never exercises the
usage row, the character budget, the feature gate, the error mapping, or the sync/async wiring;
every one of those is production code that only runs when something is stubbed *below* it. Putting
the seam at the network boundary means the facade under test is the real one.

Requirements:

- `register(text, *, target_lang, result)` and `register_error(text, *, error)`, both keyed on the
  source text so a batch can mix registered and unregistered entries.
- Records every call (`backend.calls`) so a test can assert *what was asked*, not only what came
  back.
- A **configurable `supports` set**, so **T4** is testable without shipping a second real provider —
  this is the whole reason `supports` is a constructor argument on the fake and a class constant
  everywhere else.
- An unregistered text returns a deterministic `f"[{target_lang}] {text}"` rather than raising.
  Unlike `FakeLLM`, where an unregistered call name means a test is exercising nothing and must fail
  loudly, translation has a meaningful identity transform — and the marker proves the target
  language actually propagated through the facade, which a raise would not.
- `detect()` returns a deterministic language derived from a hash of the text, so detection
  assertions are reproducible across runs.

### §4.3 What a future backend must implement

Lara and LibreTranslate are the two worked examples, and they are deliberately **not** implemented
here — a file that exists to prove a point but is never configured, never tested against a real
endpoint, and never run is worse than an interface plus a paragraph. Adding either is:

1. One member in `Settings.translation_backend`'s `Literal` (§3).
2. One file under `backends/`, subclassing `HTTPTranslationBackend` and supplying four pure
   functions plus `name` and `supports`.
3. One branch in `facade._build_backend()`.
4. One test file, transport-stubbed like `test_deepl.py`.

Nothing else — no `core/` edit outside `translation/`, no migration, no caller change. What each
would exercise that DeepL does not:

| Provider | Would exercise |
|---|---|
| LibreTranslate | Self-hosted with **no credential at all** — proves `translation_api_key` is genuinely optional per-backend rather than optional-in-principle. Has a real standalone `/detect` endpoint, so `detect()` stops being DeepL-shaped. `supports` would omit `FORMALITY`, making **T4** a live path rather than a fake-only one |
| Lara | Per-request context/instructions, which is the first thing that would want a field on `TranslateRequest` that DeepL ignores — the real test of whether the request schema generalises |

## §5. `TranslationFacade` — the module-facing surface

Constructed once in `create_app()`/`worker.py` and hung on `Platform` as `translation`, beside
`store`, `notifier`, `files` and `llm`. `Platform` gains one field; that is the only edit
`core/platform.py` takes.

```python
result = await platform.translation.translate(
    ["Hello", "Goodbye"],
    target_lang="de",
    user_id=user.id,
)
# result == [Translated(text="Hallo", detected_source_lang="EN"), Translated(text="Auf Wiedersehen", ...)]

langs = platform.translation.detect_sync(["Bonjour"])  # from a Typer command or a data migration
```

| Method | Contract |
|---|---|
| `translate(texts, *, target_lang=None, source_lang=None, formality=None, user_id=None) -> list[Translated]` | One entry per input, in input order (**T8**). Raises on budget overflow, unsupported feature, or upstream failure (§5.2) |
| `translate_sync(...)` | Identical contract, sync transport. Must not be called from inside a running event loop's thread — see §5.1 |
| `detect(texts, *, user_id=None) -> list[Detected]` | Detected language per input, in input order. Raises `TranslationNotSupported` if the backend cannot detect |
| `detect_sync(...)` | Identical contract, sync transport |
| `usage(session, *, since=None, backend=None) -> UsageSummary` | Character and call totals grouped by backend, operation and day |
| `aclose()` / `close()` | Releases the backend's HTTP clients. Called from the app lifespan |

`texts` is a `Sequence[str]` and there is no single-string convenience overload. Every provider's
endpoint is batch-native, per-string calls are the expensive mistake this API should not make easy,
and a caller with one string writes `[s]` and reads `[0]` — three characters of friction in exchange
for never accidentally issuing a hundred requests in a loop.

`target_lang` falls back to `settings.translation_default_target_lang`; with both empty the facade
raises a plain `ValueError`, not a `TranslationError`. A missing target language is a programming
error at the call site, not a translation outcome, and it must not write a usage row — the same
distinction `LLMFacade.generate()` draws when `call.schema` is `None`.

> `translate()`/`detect()` deliberately do **not** take a `session` parameter, for the same reason
> `M19` §4 gives: the `core.translation_call` row (§7) is written through the facade's own
> `session_scope()`, independent of any caller transaction, because the caller's transaction is
> exactly the one about to roll back when the call raises. `usage()` keeps its `session` parameter —
> that is a genuine read against the caller's session, not a durability write.

> **Resolved during implementation: an empty batch short-circuits.** `translate([])` and
> `detect([])` return `[]` without touching the backend and without writing a row. Zero inputs is
> zero characters and nothing was dispatched, so **T5** ("every *dispatched* call") is satisfied
> rather than bent. The alternative — raising, like the missing-`target_lang` case — would make
> `translate(items)` unsafe whenever `items` can legitimately be empty, which is most of the time.

### §5.1 Why the sync surface is real, and not `asyncio.run`

The obvious implementation of `translate_sync` is `asyncio.run(self.translate(...))`. It is wrong
twice over, and both failures are worth naming because the shortcut is genuinely tempting:

- **It raises `RuntimeError` inside a running event loop.** That makes the sync API unusable from
  `asyncio.to_thread` — which is the single place a sync API inside an async application is actually
  useful, and the one this repo would reach for first.
- **It builds and tears down an event loop, an asyncpg pool and an HTTP connection pool per call.**
  For a Typer command that translates once, that is merely wasteful; for a data migration walking a
  table, it is the difference between seconds and minutes.

So the sync path is sync all the way down: `httpx.Client` for transport (§4), and a sync SQLAlchemy
session for the usage row (§7.1). `asyncio.run` appears nowhere under `src/disp/core/translation/`,
and a test greps for it (**T3**).

The consumers this exists for: `disp-admin` and any future Typer command (`cli_admin.py:31`'s
`asyncio.run` pattern exists precisely because there was no alternative), Alembic data migrations,
and any caller already running in a worker thread.

### §5.2 Failure semantics

| Failure | Behaviour |
|---|---|
| `translation_enabled` false | `TranslationNotConfigured`. No backend was constructed, so no row is written (**T5**) |
| Feature not in `backend.supports` | `TranslationNotSupported`, raised by the backend before any request (**T4**), carrying `.backend` and `.feature` |
| Batch over `translation_max_chars` | `TranslationInputTooLarge`, raised before any network call (**T7**) |
| Connection failure / timeout | `httpx` retries per `translation_max_retries`. Exhausted → `TranslationUnavailable` |
| 5xx, 429 | `TranslationUnavailable`. Not retried — see §4's blockquote |
| 456 (DeepL quota) | `TranslationQuotaExceeded` |
| Other 4xx | `TranslationRejected` — unknown language code, malformed request, bad key |
| Unparseable payload, or wrong item count | `TranslationInvalidResponse` (**T8**) |
| No `target_lang` and no deployment default | `ValueError` — a call-site bug, not a translation outcome. No row |

**The item-count check MUST run before the results are returned, not as a caller's responsibility.**
An implementation that returns whatever the provider sent and documents "results are in order" pushes
a silent-corruption risk onto every call site, where it will be checked by none of them.

## §6. Language codes

The facade **normalises** language codes (upper-case, `_`→`-`) and **does not validate them against
a table**. An unrecognised code is the provider's error to raise — surfaced as
`TranslationRejected` — not ours to pre-empt.

A hardcoded language table is a liability: it goes stale the week a provider adds a language, it
differs per provider (DeepL's source list is a strict subset of its target list), and a client-side
rejection of a code the provider would have accepted is indistinguishable to the caller from the
provider being wrong.

The trap worth documenting for DeepL specifically: **`EN` is deprecated as a *target*** and must be
`EN-GB` or `EN-US`; the same applies to `PT-BR`/`PT-PT`. As a *source* it is fine. The facade does
not fix this up — silently rewriting `EN` to `EN-US` picks a dialect on the caller's behalf, and a
caller who meant `EN-GB` gets American spelling with no indication of why.

## §7. Usage accounting — `core.translation_call`

```sql
CREATE TABLE core.translation_call (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID,                        -- no FK: modules and core alike avoid cross-schema
                                              -- FKs (TECHNICAL-SPEC.md §6.1); NULL for
                                              -- system-initiated calls
    backend      TEXT        NOT NULL,        -- "deepl" | "fake" — TranslationBackend.name
    operation    TEXT        NOT NULL,        -- translate | detect
    source_lang  TEXT,                        -- as requested, or as detected; NULL when unknown
    target_lang  TEXT,                        -- NULL for detect
    text_count   INTEGER     NOT NULL DEFAULT 0,
    char_count   INTEGER     NOT NULL DEFAULT 0,
    latency_ms   INTEGER     NOT NULL DEFAULT 0,
    outcome      TEXT        NOT NULL,        -- ok | not_supported | unavailable | quota_exceeded
                                              --   | rejected | too_large | invalid_response
    error_code   TEXT,                        -- the core.translation.* code, if any
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_translation_call_outcome CHECK (outcome IN
        ('ok','not_supported','unavailable','quota_exceeded','rejected','too_large','invalid_response'))
);

CREATE INDEX ix_core_translation_call_created
    ON core.translation_call (created_at DESC);
CREATE INDEX ix_core_translation_call_backend_created
    ON core.translation_call (backend, created_at DESC);
```

**`char_count` is the load-bearing column.** DeepL bills per character and its free tier is a hard
monthly ceiling, so "how many characters have I spent this month" is the question this table exists
to answer — not "how many calls did I make". Count the *source* characters, which is what every
provider meters, and count them even when the call fails, because a request that reached the
provider and 5xx'd may still have been metered.

**No source text and no translated text is stored** (**T6**). The table answers "what did this cost
and did it work", not "what was said" — storing text would make every translated string readable by
anyone with database access, for a debugging benefit structured logging already provides without the
liability.

The row is written and **committed before a failure propagates** (**T5**) — the same
commit-then-raise ordering `notifier.py:_deliver_notification` uses for `notification_log` and
`llm/usage.py:write_call` uses for `core.llm_call`.

Migration: `src/disp/core/migrations/versions/0004_core_translation_call.py`, `down_revision =
"0003_core_llm_call"` (confirm that is still the core branch head before writing it), raw
`op.execute("""CREATE TABLE …""")` in `0003`'s style. ORM model `TranslationCallRow` in
`core/models.py` beside `LLMCallRow` — the `Row` suffix disambiguating it from the request
dataclasses, `__tablename__ = "translation_call"` with `{"schema": SCHEMA}`, added to `__all__`.

### §7.1 The sync session — a new core primitive

`src/disp/core/db.py` is async-only. `session_scope()` is an `@asynccontextmanager` over an
`async_sessionmaker`, and there is no sync equivalent anywhere in `src/`. The sync facade therefore
has nothing to write its row with.

Add the sync mirror of the existing pair, immediately beside it:

```python
@lru_cache
def _background_sync_session_maker() -> sessionmaker[Session]: ...


@contextmanager
def sync_session_scope(session_maker: sessionmaker[Session] | None = None) -> Iterator[Session]: ...
```

built on `sqlalchemy.create_engine(get_settings().database_url_sync)`. **No new dependency:**
`database_url_sync` already exists (`config.py:98-102`, derived from `database_url` by swapping
`+asyncpg`→`+psycopg` in a `model_validator(mode="before")`) and `psycopg[binary,pool]` is already
in `pyproject.toml` for Alembic and Procrastinate.

Two alternatives, and why each is worse:

- **The sync path writes no row.** Breaks **T5** and makes the usage table quietly wrong — the
  character total under-reports by however much the CLI and any data migration spent, which is
  exactly the usage nobody thinks to account for and therefore exactly the usage that surprises
  someone at the monthly ceiling.
- **The sync facade wraps the async one in `asyncio.run`.** §5.1.

`sync_session_scope` is a general core primitive, not a translation detail — but it is introduced
here, by the first thing that needs it, and it should be documented as such rather than presented as
part of the translation service.

> **It is deliberately *not* added to `ALLOWED_DB_NAMES`** in `tests/core/test_boundaries.py`. A
> module has no sync entry point — every module surface is a route, a job, or an event handler, all
> async — so a module reaching for a sync session is a mistake worth failing the build over rather
> than a capability worth granting. Widen the allow-list when something real needs it, with the
> reason recorded, the way `ALLOWED_AUTH_NAMES` was widened in `M06`.

## §8. Logging

One structlog line per dispatched call, at INFO on success and WARNING on failure:

```python
logger.info(
    "translation_call_completed",
    backend=backend.name,
    operation="translate",
    source_lang=source_lang,
    target_lang=target_lang,
    text_count=len(texts),
    char_count=char_count,
    latency_ms=latency_ms,
    outcome="ok",
)
```

**No source text, no translated text, no key, at any level, including DEBUG** (**T6**). A test MUST
assert this by translating a sentinel string with a sentinel key configured, capturing structlog
output, and asserting neither sentinel nor the fake's translated form appears anywhere in the
captured events — *and* that the `translation_call_completed` line was emitted at all. Asserting
only that INFO is clean would pass against an implementation that logs payloads at DEBUG; asserting
only the absence of sentinels would pass against an implementation that logs nothing.

The row write and the log line MUST happen at **one call site** (`_record`), so the two can never
drift apart — the shape `LLMFacade._record` already uses.

## §9. Module contract and boundaries

Public surface of `disp.core.translation`, importable by any module:
`TranslationFacade`, `FakeTranslationBackend`, `Feature`, `Translated`, `Detected`, `UsageSummary`,
and the error types `TranslationError`, `TranslationNotConfigured`, `TranslationNotSupported`,
`TranslationUnavailable`, `TranslationQuotaExceeded`, `TranslationRejected`,
`TranslationInputTooLarge`, `TranslationInvalidResponse`.

`tests/core/test_boundaries.py` gains an `ALLOWED_TRANSLATION_NAMES` allow-list enforcing exactly
that list, in the same shape as `ALLOWED_LLM_NAMES`. Submodules (`disp.core.translation.backends.*`,
`.facade`, `.usage`) are off-limits to modules.

**T1 is enforced by a string grep, not an import grep.** Because §4.1 chose `httpx` over the vendor
SDK there is no `import deepl` to look for — the vendor leaks through the *host name* instead. A
test asserts `deepl.com` appears in exactly one file under `src/`.

> **Resolved during implementation: those greps scan raw text, comments and docstrings included** —
> the same choice `tests/unit/tiles/no-domain-literals.test.ts` makes in the web client. Both the
> **T1** host grep and the **T3** event-loop grep caught this package's own module docstrings on
> first run, which is the test working, not the test being wrong: a comment naming the vendor host
> is exactly how the next person learns which host to hardcode. So the package's prose describes
> the provider's host and the forbidden loop-runner call *without naming either*, and says so where
> it would otherwise be tempting to name them.

The error classes are plain `Exception` subclasses, deliberately **not** `AppError` subclasses, for
the reason `llm/errors.py`'s docstring gives: these are facade-level errors a *module* catches and
translates to its own `AppError` at its own route boundary, and `core.translation` has no HTTP
endpoint of its own to translate at (§10). They need the same `N818` per-file ignore in
`pyproject.toml` that `src/disp/core/llm/errors.py` has, with the same explanatory comment.

**No `TECHNICAL-SPEC.md` Appendix A amendment.** The `core.translation.*` codes are synthesised at
the recording site as `f"core.translation.{outcome}"` and written only to
`translation_call.error_code`; they never reach a client, exactly like `core.llm.*`. Appendix A
registers codes the API *may emit*, and this service emits none. Stating that here makes the
omission a decision rather than an oversight.

## §10. HTTP API

**There is deliberately no `/api/translate` endpoint.** Such an endpoint is a cost amplifier
denominated in someone else's characters — any authenticated user could spend the deployment's
monthly quota on arbitrary text — and it belongs to no module's authorization story. Translation
reaches users only through a module's own routes, where that module has already decided who may do
what to which resource. This is the same call `M19` §11 makes about a generic "ask the model"
endpoint, for the same reason.

Nor is there an admin usage route, which *is* a departure from `M19` §11's `GET /api/llm/usage`. The
usage question here is operational rather than product-facing, and `usage()` on the facade plus
`disp-admin translation usage` (`core/cli_admin_translation.py`, registered as a sub-Typer beside
`disp-admin files`) answers it without adding a router, a response model, and an auth surface to a
service that otherwise has none. Add the HTTP route when a client needs to render it, not before.

`usage --days N [--backend NAME]` prints one line per (day, backend, operation, outcome) group plus
a total. Like every other `disp-admin` command it has no `Platform`, so it builds its own engine and
disposes it in a `finally` — the shape `seed_admin` established.

## §11. Testing

- **No network in the test suite, ever.** Both DeepL transports are exercised against
  `httpx.MockTransport`; everything else uses the fake backend. A test that reaches `deepl.com` is a
  failed test even when it passes.
- **Sync/async parity (T2).** Run identical input through `translate` and `translate_sync` with
  request-capturing mock transports on both, and assert the captured method, URL, headers and body
  are equal *and* the results are equal. Asserting only that both return the right answer would pass
  against two implementations that diverge on everything an assertion does not cover — which is
  where the bug would be.
- **Feature gate (T4).** Construct the fake with `supports` omitting `FORMALITY`, request formality,
  assert `TranslationNotSupported` **and** that the transport saw no request. Asserting only the
  exception type would pass against an implementation that calls first and checks the response.
- **Usage durability (T5).** A call that raises still leaves its row committed — assert from a
  *separate* session, since asserting inside the caller's rolled-back transaction proves nothing.
  Assert the sync path's row lands too, through `sync_session_scope`.
- **`TranslationNotConfigured` writes no row.** Assert the row count is unchanged, not merely that
  the exception was raised.
- **Budget (T7).** A batch above `translation_max_chars` raises with the transport never seeing a
  request.
- **Item-count mismatch (T8).** A mock transport returning one result for two inputs raises
  `TranslationInvalidResponse` — not an `IndexError`, and not a silently short list.
- **DeepL specifics.** Base URL derived from a `:fx` key vs a pro key vs an explicit
  `translation_base_url`; `456`→`TranslationQuotaExceeded`, other 4xx→`TranslationRejected`,
  5xx→`TranslationUnavailable`; the `DeepL-Auth-Key` header shape.
- **Log hygiene (T6).** The sentinel test in §8.
- **No event loop (T3).** `grep` the package for `asyncio.run`.
- **Boundaries.** `tests/core/test_boundaries.py` rejects a module importing
  `disp.core.translation.backends.deepl`, and `deepl.com` appears in one file.

Tests live in `tests/core/translation/`, with no `__init__.py`, matching `tests/core/llm/`.

> **Resolved during implementation, twice, both about test files.**
>
> **Basenames are globally unique across `tests/`, not per-directory.** With no `__init__.py`
> anywhere under `tests/`, pytest derives a module name from the basename alone, so a second
> `test_facade.py` collides with `tests/core/llm/test_facade.py` at *collection* time and takes five
> other files down with it. Hence `test_translation_facade.py`, `test_fake_backend.py`, and so on.
> Every existing test directory already obeys this; it is a convention nothing had written down.
>
> **The sync tests need their own fixtures, so this directory does keep a small local one — inline
> in `test_translation_facade_sync.py` rather than a `conftest.py`.** The root conftest's
> `db_connection`/`session_maker` pair is async; `sync_session_scope` issues a real `COMMIT`, so
> without a sync mirror (a psycopg connection, one outer transaction, sessions joined by SAVEPOINT,
> rolled back after) every sync test would leak rows past the per-test boundary and every count
> assertion in the directory would silently depend on run order.

Coverage: `src/disp/core/translation/` warrants a **≥95%** gate, like `src/disp/core/auth/`,
`core/files/` and `core/llm/` — it holds a credential and spends money. Unlike when `M19` was
written, the machinery now exists: `./dev` (`:96-110`) already runs one
`coverage report --include=… --fail-under=95` per gated directory over the shared `.coverage` file.
This milestone adds a fourth invocation — the "one line" `M19` §12 predicted.

Also confirm `concurrency = ["greenlet", "thread"]` is still set in `[tool.coverage.run]` before
believing any low number this produces.

## §12. Operations (`docs/operations.md` amendments)

- `DISP_TRANSLATION_API_KEY` joins `DISP_LLM_API_KEY` and `DISP_EMBEDDING_API_KEY` in the "lives
  only in the environment" section (`:150`) and the rotation table (`:235`). Like those, losing it
  destroys nothing — it is re-issuable from the provider. Say so explicitly, so an operator does not
  treat a rotation as a data-loss event.
- Rotation is a restart: change the env var, `docker compose up -d api worker`. No re-encryption
  step, unlike `DISP_SETTINGS_KEY`. In-flight calls at the moment of restart fail and are recorded
  with `outcome='unavailable'`; nothing is silently dropped.
- **Switching a free-tier key for a pro key changes the API host.** If `DISP_TRANSLATION_BASE_URL`
  was ever set explicitly, it must be cleared or updated at the same time, or every call 403s. This
  is the one rotation in this repo that is not purely "swap the value".
- Character-budget monitoring: `disp-admin translation usage`, plus the `core.translation_call`
  table for anything the command does not aggregate. Note that a free-tier account's ceiling is
  monthly and resets on the billing date, not the 1st.
- No new volume, no new service, no image change. `.env.example` gains the `DISP_TRANSLATION_*`
  block, disabled by default.

## §13. Out of scope

A translation cache (§13's blockquote); glossaries and translation memory; document/file translation
(DeepL's `/v2/document` is an async three-call upload/poll/download flow, a different shape
entirely); HTML/XML tag handling beyond passing the provider's own flag through; per-user quota
*enforcement* (`usage()` reports; nothing blocks on it); a `languages()` method listing what the
backend supports (§6 argues against holding a language table at all, and the same argument applies
to caching the provider's); retry-with-backoff over HTTP status codes (§4); multi-provider fallback;
an HTTP route (§10); a settings panel (§3).

> **The cache deserves a decision rather than silent omission.** Translation is a pure function of
> (text, source, target, backend, formality), the results are stable for months, and the same UI
> strings will be translated over and over — so a cache keyed on a hash of exactly those five things
> would cut the character bill by more than any other change available. It is out of scope here
> because it needs an invalidation story (what happens when a provider improves, or a backend
> changes) and a size bound, not because it is unimportant. Make the call before the first
> high-volume caller lands, not after the first bill.

## Dependencies

Core only — `Settings` (M1), `core` models and Alembic branch (M2, M5), `Platform` construction in
`create_app()` and `worker.py` (M10), the three-segment error-code shape (M21). Independent of
`M18`, `M19` and `M20`, though it copies `M19`'s facade, accounting and boundary-test patterns
almost verbatim, and `M18` §6's `StorageBackend` protocol shape.

## Verification

- `./dev lint` clean — note `mypy` runs `strict = true` over `disp.core.*`, so the Protocol and the
  dual-transport base must be fully typed.
- `./dev test` green with the new `≥95%` per-directory coverage gate on `src/disp/core/translation/`.
- `grep -rn "deepl\.com" src/` returns exactly one file (**T1**).
- `grep -rn "asyncio\.run" src/disp/core/translation/` returns nothing (**T3**).
- Boot with `DISP_TRANSLATION_ENABLED=false` and no key — the common case for a deployment that
  wants no translation — and confirm the app starts and the facade raises `TranslationNotConfigured`.
- Set `DISP_TRANSLATION_ENABLED=true` with an empty key and the `deepl` backend, and confirm the app
  **refuses to start** rather than failing at first use. Then set `DISP_TRANSLATION_BACKEND=fake`
  with the key still empty and confirm it starts — that conditional is the point of §3's validator.
- With `DISP_TRANSLATION_BACKEND=fake`, make one async call and one sync call, then confirm two
  `core.translation_call` rows with the right `char_count` and `backend` (`./dev shell`).
- **Run the built image, don't just build it** — `docker compose up`, then one live DeepL call with
  a real free-tier key (`:fx` suffix) to prove the base-URL derivation actually fires, and one with
  a pro key if available. Both of this repo's Docker bugs were found by running the image, never by
  building it (`CLAUDE.md`).
- Point `DISP_TRANSLATION_BACKEND` at `fake` and back at `deepl` and confirm **no caller code
  changes** — that substitutability is this milestone's actual thesis, and the only test of it is
  doing it.
