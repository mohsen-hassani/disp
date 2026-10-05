# M19 — core LLM service

**Status:** Implemented. `src/disp/core/llm/` exists and `./dev lint`/`./dev test` are green,
including the new ≥95% coverage gate. Six spec ambiguities were resolved during implementation and
are recorded inline where they matter (§4's dropped `session` parameter, §6's `LLMNotConfigured`
no-row rule, §11's `/api/llm/usage` path, among others) — see this file's amended §4 and §11 for the
corrected contracts. **Not yet done:** distilling this document into `docs/llm.md` and reducing this
file to a build log, per this section's own instruction below.

**Scope:** new package `src/disp/core/llm/` (`__init__.py`, `client.py`, `schema.py`, `budget.py`,
`embeddings.py`, `usage.py`, `errors.py`, `fake.py`), a `core.llm_call` table + core Alembic
revision, `LLMFacade` on `Platform` as `llm`, `DISP_LLM_*` and `DISP_EMBEDDING_*` settings, and a
`pgvector/pgvector:pg16` image swap across the three compose files and the test container.

**Covers:** nothing in `TECHNICAL-SPEC.md` — the backbone spec predates any AI capability in this
platform. Like `src/disp/modules/plants/TECHNICAL-SPEC.md` and `M18-files.md`, this document is
therefore *normative for itself*: it is the source of truth for anything under `src/disp/core/llm/`,
not a summary of a spec section elsewhere. When implementation lands, distil the as-built reality
into `docs/llm.md` and reduce this file to a build log, the way `M00`–`M16` read today.

---

## §1. Why this exists

`M20` (the `learning` module) needs an LLM for eleven distinct call sites — source segmentation,
topic alignment, tag generation, path generation, quiz generation, quiz grading, exercise
generation, exercise grading, chat, explain/guide/summarize, and freeform retrieval. It also needs
embeddings. None of that exists in this repo today: `pyproject.toml` has no LLM SDK, `core/config.py`
has no API-key field, and nothing anywhere calls a model.

The tempting shortcut is `learning/llm.py` — a module-owned client, the way `plants/config.py` owns
`DISP_PLANTS_*`. That shortcut is wrong here, and `M18` §1 already documents why in a different
domain: `plants` invented private media storage because nothing shared existed, and the platform
consequently acquired a bespoke backup path, a bespoke sniffing table, and two chances to get
path traversal wrong. An LLM client is a worse thing to duplicate than a storage helper. It holds a
credential, it spends money per call, it needs retry and timeout policy, it needs token accounting,
and it needs a test double — and every one of those is a cross-cutting concern that a second AI
module would have to reimplement or, more likely, copy.

Three problems this fixes on the way:

1. **No module may add a field to core `Settings`.** `src/disp/core/config.py` sets
   `extra="forbid"`, and `tests/core/test_plugin_proof.py` asserts that adding a module changes zero
   files under `src/disp/core/`. A module-owned API key therefore has to live in a module-owned
   `BaseSettings` — which means the credential's lifecycle, rotation, and startup validation are
   invented once per module rather than once per platform.
2. **Nothing in this codebase can currently be tested against a model.** The test suite is
   hermetic (`tests/conftest.py` starts real Postgres and forbids SQLite). A module that calls an
   API directly is either untestable or grows its own monkeypatch surface. §9's `FakeLLM` is the
   piece that makes eleven LLM-dependent call sites testable at all.
3. **Cost is invisible.** There is no accounting surface anywhere. §6's `core.llm_call` table means
   the first question anyone asks in production — *what is this costing me* — has an answer that
   does not require a provider dashboard.

**The central design decision** is that the facade's primary interface is **schema-validated
structured output**, not text. `generate()` takes a Pydantic model and returns a validated instance
of it; free text is the narrow special case (`generate_text()`), not the default. This is what stops
malformed model output from ever reaching a database write, and it is what makes the eleven call
contracts in `M20` §12 into type signatures rather than prose.

**A consequence worth stating up front:** Anthropic publishes no embeddings endpoint. The
LLM provider and the embedding provider are therefore **different vendors**, and §7 treats
embeddings as a separately configured, separately swappable concern rather than a method on the
same client. A design that assumes one credential and one base URL for both would have to be
unpicked later.

## §2. Concepts and invariants

- **Call** — one logical request to a model, named `<domain>.<name>` (`KEY_RE`, the same pattern
  scheduler tasks and manifest keys use). The name is not cosmetic: it is the grouping key for usage
  accounting (§6) and the lookup key for `FakeLLM` responses (§9).
- **Facade** — `platform.llm`. The only surface a module may touch. Which provider, which model, and
  which retry policy sit behind it are deployment concerns a module cannot observe.
- **Output schema** — a Pydantic model class the caller passes in and gets an instance of back.
- **Budget** — the token accounting for one call: what the input costs, what the ceiling is, and
  what to do when the input exceeds it (§5).

Invariants, each of which a test must pin:

- **L1** A `generate()` call returns a validated instance of the caller's schema, or raises. It
  never returns raw text, a `dict`, or a partially-populated model.
- **L2** No prompt, no completion, and no API key is ever written to a log at any level. Log lines
  carry the call name, model, token counts, latency, and outcome — nothing else. (§8)
- **L3** Every call writes exactly one `core.llm_call` row, including failed and refused ones. The
  row is committed even when the call raises (§6) — the same commit-then-raise ordering
  `notifier.py:_deliver_notification` already uses so a retry never loses the audit record.
- **L4** A module cannot observe which provider is in use. `disp.core.llm`'s public surface names no
  vendor, and `anthropic` is imported in `client.py` only.
- **L5** Input that exceeds the call's budget raises `LLMInputTooLarge` **before** any network
  request. The facade never silently truncates a caller's input.
- **L6** A `stop_reason` of `"refusal"` is surfaced as `LLMRefused`, never as empty output.
- **L7** Embedding vectors are dimension-checked against the configured model on write. A dimension
  mismatch raises rather than storing a vector the index cannot compare.

## §3. Configuration

Added to core `Settings` (`src/disp/core/config.py`, env prefix `DISP_`). `model_config` sets
`extra="forbid"`, so every one of these must exist as a field on the class — an env var alone will
not do, unlike the module-owned `DISP_PLANTS_*` settings, which pydantic-settings ignores by prefix.

| Field | Env | Default | Notes |
|---|---|---|---|
| `llm_enabled` | `DISP_LLM_ENABLED` | `false` | When false, the facade raises `LLMNotConfigured` on every call. Keeps a deployment that wants no AI from needing a key |
| `llm_api_key` | `DISP_LLM_API_KEY` | `SecretStr("")` | |
| `llm_model` | `DISP_LLM_MODEL` | `claude-opus-5` | Default model for calls that do not name one |
| `llm_fast_model` | `DISP_LLM_FAST_MODEL` | `claude-haiku-4-5` | For high-volume, low-judgement calls (§4.2) |
| `llm_max_output_tokens` | `DISP_LLM_MAX_OUTPUT_TOKENS` | `16000` | Hard ceiling; a `LLMCall` may be stricter, never looser |
| `llm_timeout_seconds` | `DISP_LLM_TIMEOUT_SECONDS` | `600` | `ge=10, le=1800` |
| `llm_max_retries` | `DISP_LLM_MAX_RETRIES` | `2` | Passed to the SDK, which already retries 408/409/429/5xx with backoff |
| `llm_effort` | `DISP_LLM_EFFORT` | `high` | `low` \| `medium` \| `high` \| `xhigh` \| `max` |
| `embedding_enabled` | `DISP_EMBEDDING_ENABLED` | `false` | Independent of `llm_enabled` — see §7 |
| `embedding_provider` | `DISP_EMBEDDING_PROVIDER` | `voyage` | `voyage` \| `local` |
| `embedding_api_key` | `DISP_EMBEDDING_API_KEY` | `SecretStr("")` | |
| `embedding_model` | `DISP_EMBEDDING_MODEL` | `voyage-3` | |
| `embedding_dimensions` | `DISP_EMBEDDING_DIMENSIONS` | `1024` | Must match the model. Pinned in config because the DDL's `vector(N)` column has to agree (§7) |

A `model_validator(mode="after")` MUST reject `llm_enabled=true` with an empty `llm_api_key`, and
`embedding_enabled=true` with an empty `embedding_api_key` when the provider is `voyage`, in the
style of the existing `_validate_production_cookie_secure`. Failing at startup is the point: a
deployment whose ingestion jobs all fail two minutes into a worker run is worse than one that
refuses to boot.

> **Do not put the API key in the settings store.** It is a deployment secret, like
> `DISP_SETTINGS_KEY` — and putting it in `core.settings` would be circular, since the settings
> store needs `DISP_SETTINGS_KEY` to decrypt its own secret fields before it could produce this one.
> A `core.llm` settings panel MAY expose non-secret preferences (model choice, effort) later; the
> credential stays in the environment.

## §4. `LLMFacade` — the module-facing surface

Constructed once in `create_app()`/`worker.py` and hung on `Platform` as `llm`, beside `store`,
`notifier`, and `scheduler`. `Platform` gains one field; that is the only edit `core/platform.py`
takes.

```python
class TopicAlignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topics: list[AlignedTopic]
    unmatched_section_ids: list[UUID]


result: TopicAlignment = await platform.llm.generate(
    call=LLMCall(
        name="learning.align_topics",
        schema=TopicAlignment,
        system=ALIGNMENT_SYSTEM_PROMPT,  # stable prefix — cached (§4.3)
        max_output_tokens=8000,
    ),
    user_content=headings_payload,
    user_id=user.id,
)
```

| Method | Contract |
|---|---|
| `generate(call, user_content, *, user_id, model=None) -> T` | Validated instance of `call.schema`. Raises on refusal, budget overflow, or schema failure after repair (§4.4) |
| `generate_text(call, user_content, *, user_id, model=None) -> str` | For genuinely free-form output (chat replies, markdown explanations). `call.schema` MUST be `None` |
| `count_tokens(call, user_content, *, model=None) -> int` | Provider-accurate count via the SDK's token-counting endpoint. **Never** an estimate |
| `embed(texts, *, user_id) -> list[list[float]]` | §7. Raises `LLMNotConfigured` when `embedding_enabled` is false |
| `usage(session, *, since=None, call_name=None) -> UsageSummary` | Token and call totals for the admin view |

> `generate()`/`generate_text()`/`embed()` deliberately do **not** take a `session` parameter. The
> `core.llm_call` usage row (§6) is written through the facade's own `session_scope()`, independent
> of any caller transaction — a caller-supplied session would never be read. `usage()` keeps its
> `session` parameter: that call is a genuine read against the caller's session, not a durability
> write, so there's no reason to duplicate it.

`LLMCall` is a frozen dataclass: `name` (must match `KEY_RE`), `schema` (`type[BaseModel] | None`),
`system` (str), `max_output_tokens` (clamped to `settings.llm_max_output_tokens` — a caller may
tighten the platform limit, never loosen it), `effort`, and `max_input_tokens`.

### §4.1 Why the schema is on the call, not the response

The alternative — return text and let the caller parse — is what every one of `M20`'s eleven call
sites would then implement, eleven slightly different ways, each with its own JSON-repair loop.
Putting the schema on the call means the provider's own structured-output support does the work
(`output_config.format` with a `json_schema`, or the SDK's `messages.parse()` helper), and the
caller receives something already validated by Pydantic. The eleven contracts in `M20` §12 are then
literally the eleven schema classes.

### §4.2 Model selection

`settings.llm_model` (`claude-opus-5`) is the default. A call may pass `model=` explicitly; the
intended use is `settings.llm_fast_model` for high-volume, low-judgement work. Modules MUST NOT
hardcode a model ID — they name the *tier* they want and the facade resolves it, so a model upgrade
is a config change rather than a code change across every module.

**Do not downgrade a call to a cheaper model to save cost without evidence.** Grading a user's quiz
answer is judgement work and belongs on the default model; tokenising an SRT transcript into
labelled ranges is closer to extraction and is a reasonable candidate for the fast model. Decide per
call site, in `M20` §12, not globally here.

### §4.3 Prompt caching

Every `LLMCall` carries a `system` prompt that is constant for that call site. The facade MUST send
it as a cached prefix (`cache_control: {"type": "ephemeral"}` on the last system block), because the
render order is `tools` → `system` → `messages` and the volatile per-request payload therefore
lands after the breakpoint by construction.

Two consequences the implementer must respect:

- **The system prompt must be a module-level constant, never an f-string built per request.** A
  timestamp, a user id, or a `datetime.now()` interpolated into it changes the prefix bytes on every
  call and the cache read rate silently goes to zero.
- **The minimum cacheable prefix is 512 tokens on `claude-opus-5`.** Below that, caching is a no-op
  — no error, just `cache_creation_input_tokens: 0`. Short prompts are fine; do not pad them to
  reach the threshold.

A test MUST assert `usage.cache_read_input_tokens > 0` on the second of two identical calls against
the fake — or, if that is not observable in the fake, assert that the rendered system block carries
the cache marker and is byte-identical across two constructions.

### §4.4 Failure semantics

| Failure | Behaviour |
|---|---|
| Transport/5xx/429 | The SDK retries per `llm_max_retries` with backoff. Exhausted → `LLMUnavailable` |
| `stop_reason == "refusal"` | `LLMRefused`, carrying `stop_details.category` when present (**L6**) |
| `stop_reason == "max_tokens"` | `LLMTruncated`. Not retried — a larger `max_output_tokens` is a code change, not a runtime decision |
| Schema validation fails | **One** repair attempt: re-send with the validation error appended as a user turn. Second failure → `LLMInvalidOutput` |
| Input over budget | `LLMInputTooLarge`, raised before any network call (**L5**) |
| `llm_enabled` false | `LLMNotConfigured` |

**`stop_reason` MUST be checked before reading `response.content`.** A refusal returns HTTP 200 with
an empty or partial content array; code that indexes `content[0]` unconditionally raises an
`IndexError` that looks like a bug in the caller rather than a policy outcome.

The single repair attempt is deliberate. Unbounded repair loops on a paid API are how a malformed
prompt becomes a large invoice; two attempts is enough to absorb a transient formatting slip and not
enough to matter if the schema is genuinely wrong.

## §5. Budgets and chunking — `budget.py`

`count_tokens()` uses the provider's own token-counting endpoint. **`tiktoken` and every other
client-side estimator are forbidden**: they are calibrated for a different tokenizer and undercount
by 15–20% on prose and considerably more on code, which is exactly the direction that turns a
"safely under budget" check into a 400 in production.

`LLMCall.max_input_tokens` defaults to a conservative fraction of the model's context window.
Exceeding it raises (**L5**) rather than truncating, because a silently truncated source document
produces a *plausible* topic list that is missing half the material — a failure with no visible
symptom, which is the worst kind.

The facade offers `chunk_text(text, *, max_tokens, overlap_tokens) -> list[str]` for callers that
must map-reduce. It splits on paragraph boundaries where possible and never mid-word. **The facade
does not decide when to chunk** — that is a caller's judgement, because the reduce step is
domain-specific (see `M20` §5.1, where SRT segmentation map-reduces and heading alignment does not).

## §6. Usage accounting — `core.llm_call`

```sql
CREATE TABLE core.llm_call (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID,                        -- no FK: modules and core alike avoid
                                                    -- cross-schema FKs (TECHNICAL-SPEC.md §6.1);
                                                    -- NULL for system-initiated calls
    call_name          TEXT        NOT NULL,        -- "<domain>.<name>", KEY_RE
    model              TEXT        NOT NULL,
    input_tokens       INTEGER     NOT NULL DEFAULT 0,
    cached_read_tokens INTEGER     NOT NULL DEFAULT 0,
    output_tokens      INTEGER     NOT NULL DEFAULT 0,
    latency_ms         INTEGER     NOT NULL DEFAULT 0,
    outcome            TEXT        NOT NULL,        -- ok | refused | truncated | invalid_output
                                                    --   | unavailable | too_large
    error_code         TEXT,                        -- the `learning.*`/`core.llm.*` code, if any
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_llm_call_outcome CHECK (outcome IN
        ('ok','refused','truncated','invalid_output','unavailable','too_large'))
);

CREATE INDEX ix_core_llm_call_created ON core.llm_call (created_at DESC);
CREATE INDEX ix_core_llm_call_name_created ON core.llm_call (call_name, created_at DESC);
```

**No prompt or completion text is stored** (**L2**). The table answers "what did this cost and did
it work", not "what was said" — storing prompts would make every user's learning material readable
by anyone with database access, for a debugging benefit that structured logging already provides
without the liability.

The row is written and **committed before a failure propagates** (**L3**). Concretely: the facade
opens its own short-lived `session_scope()` for the usage row rather than piggy-backing on a
caller-supplied session — which is also why `generate()`/`generate_text()`/`embed()` take no
`session` parameter at all (§4): the caller's transaction is exactly the one that is about to roll
back when the call raises, so accepting one would invite exactly the bug this mechanism exists to
avoid.

## §7. Embeddings — a separate provider

**Anthropic publishes no embeddings endpoint.** This is the single most consequential fact in this
milestone and it must not be discovered during implementation: `platform.llm.embed()` talks to a
different vendor, with a different key, a different base URL, and a different failure mode from
every other method on the same facade.

`EmbeddingProvider` is a protocol with two shipped implementations:

| Backend | `DISP_EMBEDDING_PROVIDER` | Notes |
|---|---|---|
| Voyage AI | `voyage` | The default. `voyage-3`, 1024 dimensions. HTTP via `httpx`, already a dependency |
| Local | `local` | `sentence-transformers` behind an optional extra. No network, no key, no per-token cost; a meaningfully worse retrieval quality and a large image. For deployments that will not send text to a third party |

`embed()` batches, and MUST assert every returned vector's length equals
`settings.embedding_dimensions` before returning (**L7**). The check is cheap and the failure it
prevents is not: a `vector(1024)` column silently rejecting or mis-indexing a 1536-dimension vector
produces retrieval that is wrong rather than absent.

**pgvector is not installed.** All three compose files (`docker-compose.yml`,
`docker-compose.test.yml`, `docker-compose.e2e.yml`) use stock `postgres:16-alpine`, and
`tests/conftest.py` starts a bare `postgres:16` testcontainer. This milestone swaps all four to
`pgvector/pgvector:pg16`. The `CREATE EXTENSION IF NOT EXISTS vector` statement belongs in the
**consuming module's** first migration, not in a core one — core has no vector column of its own,
and a module that does not use embeddings should not pay for the extension.

## §8. Logging

One structlog line per call, at INFO on success and WARNING on failure:

```python
logger.info(
    "llm_call_completed",
    call_name=call.name,
    model=model,
    outcome="ok",
    input_tokens=...,
    cached_read_tokens=...,
    output_tokens=...,
    latency_ms=...,
)
```

**No prompt, no completion, no key, at any level, including DEBUG** (**L2**). A test MUST assert
this by capturing structlog output for a call whose prompt contains a sentinel string and asserting
the sentinel appears nowhere in the captured events. Asserting only that INFO is clean would pass
against an implementation that logs prompts at DEBUG, and a production deployment that turns on
debug logging to chase a bug should not thereby start writing users' private study material to
disk.

## §9. `FakeLLM` — the test double

Shipped in `disp.core.llm.fake` and part of the public surface, because module tests need it.

```python
fake = FakeLLM()
fake.register("learning.align_topics", TopicAlignment(topics=[...], unmatched_section_ids=[]))
fake.register_error("learning.grade_quiz", LLMRefused(category="cyber"))
platform.llm = fake
```

Requirements:

- Returns registered responses **by call name**, validating them against the call's schema on
  registration — a fake that returns something the real schema would reject is worse than no fake,
  because it makes the test pass and production fail.
- Records every call (`fake.calls`) so a test can assert *what was asked*, not only what came back.
- An unregistered call name raises loudly. Silence would let a test pass while exercising nothing.
- `embed()` returns deterministic vectors derived from a hash of the input text, of exactly
  `settings.embedding_dimensions` length — so similarity assertions are reproducible and the
  dimension invariant (**L7**) is exercised in tests too.

## §10. Module contract and boundaries

Public surface of `disp.core.llm`, importable by any module:
`LLMFacade`, `LLMCall`, `FakeLLM`, `UsageSummary`, and the error types `LLMError`,
`LLMNotConfigured`, `LLMUnavailable`, `LLMRefused`, `LLMTruncated`, `LLMInvalidOutput`,
`LLMInputTooLarge`.

`tests/core/test_boundaries.py` gains an `ALLOWED_LLM_NAMES` allow-list enforcing exactly that list,
in the same shape as `ALLOWED_AUTH_NAMES` and `ALLOWED_DB_NAMES`. Submodules
(`disp.core.llm.client`, `.embeddings`, `.usage`, `.budget`) are off-limits to modules, like
`disp.core.auth`'s internals — and in particular a module importing `disp.core.llm.client` would be
importing the vendor SDK transitively, defeating **L4**.

`anthropic` appears in `pyproject.toml` as a first-class dependency and is imported in exactly one
file. A test MUST assert that: grep the tree for `import anthropic` outside `core/llm/client.py`.

## §11. HTTP API

**There is deliberately no generic "ask the model" endpoint.** Such an endpoint is an
unauthenticated-in-effect cost amplifier — any user could spend the deployment's budget on anything
— and it belongs to no module's authorization story. LLM access reaches users only through a
module's own routes, where that module has already decided who may do what.

One admin-only exception: `GET /api/llm/usage`, mounted with the other core routers under the
`llm` domain's own namespace (matching every other admin-gated route's per-resource convention —
`/api/settings/...`, `/api/auth/...` — rather than introducing a shared `/api/admin/*` prefix that
would be the first of its kind in this codebase), returning `UsageSummary` grouped by call name and
day. Gated with `require_admin`.

## §12. Testing

- **No network in the test suite, ever.** The provider client is exercised against a transport-level
  stub; every other test uses `FakeLLM`. A test that reaches api.anthropic.com is a failed test even
  when it passes.
- **Schema-validation path.** Assert that malformed output triggers exactly one repair attempt and
  that a second failure raises `LLMInvalidOutput` — asserting only the final exception would pass
  against an implementation that never repairs, and against one that repairs forever.
- **Refusal path.** A `stop_reason: "refusal"` response raises `LLMRefused` and writes a
  `core.llm_call` row with `outcome='refused'`.
- **Usage durability.** A call that raises still leaves its row committed (**L3**) — assert from a
  *separate* session, since asserting inside the caller's rolled-back transaction proves nothing.
- **Budget.** Input above `max_input_tokens` raises with the transport stub never seeing a request
  (**L5**). Asserting only on the exception type would pass against an implementation that calls
  first and checks after.
- **Log hygiene.** The sentinel test in §8.
- **Boundaries.** `tests/core/test_boundaries.py` rejects a module importing `disp.core.llm.client`.
- **Embedding dimensions.** A provider returning the wrong length raises (**L7**).

Coverage: `src/disp/core/llm/` warrants a **≥95%** gate, like `src/disp/core/auth/` — it holds a
credential and spends money. Note that gate does not currently exist as machinery: `./dev test`
enforces only the global `--cov-fail-under=85`, and the auth `≥95%` figure in `CLAUDE.md` is
enforced by nothing. This milestone (or `M18`, whichever lands first) should add the machinery.

**Not** in the shape the web client uses: `vitest.config.ts`'s glob-keyed `coverage.thresholds` is a
Vitest feature and `coverage.py` has no per-path threshold equivalent. `M18` §14 specifies the
portable form — additional `coverage report --include='src/disp/core/llm/*' --fail-under=95`
invocations in `./dev test`, one per gated directory, after the main run. Whichever milestone lands
first adds the mechanism and the auth gate; the second adds one line.

Also confirm `concurrency = ["greenlet", "thread"]` is still set before believing any low number this
produces.

## §13. Operations (`docs/operations.md` amendments)

- `DISP_LLM_API_KEY` and `DISP_EMBEDDING_API_KEY` join `DISP_SETTINGS_KEY` in the "needs its own
  backup" section — except that unlike `DISP_SETTINGS_KEY`, losing them destroys nothing; they are
  re-issuable from the provider. Say so explicitly, so an operator does not treat a rotation as a
  data-loss event.
- Rotation is a restart: change the env var, `docker compose up -d api worker`. No re-encryption
  step, unlike `DISP_SETTINGS_KEY`.
- The Postgres image change (§7) is a **rebuild, not a data migration** — `pgvector/pgvector:pg16`
  is the same Postgres 16 with an extension available. Existing volumes mount unchanged. Say this
  plainly; an operator who reads "new database image" and plans a dump/restore window is doing
  unnecessary work.
- Cost monitoring: `GET /api/llm/usage`, plus the `core.llm_call` table for anything the
  endpoint does not aggregate.

## §14. Out of scope

Streaming responses (no `StreamingResponse` exists anywhere in `src/` yet; the generated web client
already ships an unused `serverSentEvents.gen.ts`, so the client half is free when someone wants
it); the Batches API (50% cheaper, hours of latency — a good fit for bulk tag generation, additive
later); tool use / function calling; multi-provider fallback; per-user quota *enforcement*
(`usage()` reports; nothing blocks on it); prompt versioning and A/B testing; a `core.llm` settings
panel.

> Streaming deserves a decision rather than silent omission. Chat and explain are the two call sites
> where a multi-second wait with no output is a visibly worse product, and they are `M20`'s most
> interactive surfaces. It is out of scope here because it needs an SSE story on both sides of the
> wire — not because it is unimportant. Make the call explicitly when `M20` §10 is built.

## Dependencies

Core only — `Settings` (M1), `core` models and Alembic branch (M2, M5), auth dependencies for the
admin usage route (M6), `Platform` construction in `create_app()` and `worker.py` (M10).
Independent of `M18`; `M20` depends on both.

## Verification

- `./dev test` green with the new per-directory coverage gate; `./dev lint` clean.
- `grep -rn "import anthropic" src/` returns exactly one file.
- **Run the built image, don't just build it** — `docker compose up`, confirm the app boots with
  `DISP_LLM_ENABLED=false` and no key set (the common case for a deployment that wants no AI), then
  again with a real key and a single live call. Both of this repo's Docker bugs were found by
  running the image, never by building it (`CLAUDE.md`).
- Set `DISP_LLM_ENABLED=true` with an empty key and confirm the app **refuses to start** rather than
  failing at first use.
- `CREATE EXTENSION vector` succeeds against the swapped Postgres image in all three compose files
  *and* in the testcontainer.
- Point `DISP_EMBEDDING_PROVIDER` at `local`, re-run the embedding tests, and confirm **no module
  code changes** — that substitutability is this section's actual thesis, and the only test of it is
  doing it.
