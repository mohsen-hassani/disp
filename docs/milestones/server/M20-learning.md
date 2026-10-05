# M20 — learning module

**Status:** Phases 1–9 implemented in code; the manual verification pass is not done.
`src/disp/modules/learning/` has the schema (migrations `0001`, `0002`, the `[learning]` alembic
branch), course CRUD, source ingestion (`service/ingest.py`), indexing and path generation as the
`learning.index_course` / `learning.generate_path` tasks on the `learning` queue (`service/jobs.py`,
`service/path.py`), quiz and exercise sessions (`service/sessions.py`), explain/chat and notes
(`service/chat.py`, `service/notes.py`), mastery (`service/mastery.py`), the dashboard tile
(`tiles.py`), the settings panel and the `learning.daily_nudge` reminder (`manifest.py`,
`reminders.py`) — about 47 routes in `router.py`, covered by the `tests/modules/test_learning*.py`
files. The web client (Phase 9) has all eight screens (`clients/web/src/routes/_app.learning.*`,
`clients/web/src/components/learning/`, `useLearningJob`), with `learning` registered in
`MODULE_SCREENS`, unit tests and `tests/e2e/learning.spec.ts`. `./dev lint`, `./dev test` (541
passed) and `pnpm test` (316 passed) were green when this was committed.
**Not yet done:** the checks in "Verification" below (running the built image against a real book,
the `DISP_LLM_ENABLED=false` boot, re-index with mastery history, concurrent indexes, the
`internal_rubric` leak grep), and `pnpm test:e2e` has not been run against the composed stack. The
`media` volume in §13 no longer applies: uploads go through `core.files` (S3), per M18 v2.

**Scope:** new module `src/disp/modules/learning/` (manifest, config, models, schemas, LLM schemas,
prompts, a four-file service package, router, tiles, events, Alembic branch), two Procrastinate
tasks on a dedicated queue, a `learning.job` status surface, eight web-client screens, and compose
amendments for the worker's media mount.

**Covers:** nothing in `TECHNICAL-SPEC.md`. The normative reference is
[`src/disp/modules/learning/TECHNICAL-SPEC.md`](../src/disp/modules/learning/TECHNICAL-SPEC.md) —
written prospectively, in the shape `plants/TECHNICAL-SPEC.md` takes retrospectively. **That
document is the source of truth; this one is the order to build it in.** Where they disagree, the
module spec wins. When implementation lands, distil the as-built reality back into the module spec
and reduce this file to a build log, the way `M00`–`M16` read today.

The origin document is `learning-platform-technical-spec.md` at the repo root — a
provider-agnostic draft that explicitly deferred "auth, module registration/routing conventions, job
queue choice, embedding provider, and general code layout" to the host project. Every one of those
is a build-failing constraint in DISP rather than a convention, which is what the module spec exists
to resolve. **Delete the root draft once this milestone is approved** — two specs for one module is
how they drift.

---

## §1. Why the order matters

The temptation is to build the data model and the LLM calls together, because the LLM calls are the
interesting part. Don't. Three properties of this module make the sequence below non-arbitrary:

1. **§8.1 of the module spec — parsing and sectioning — is entirely deterministic.** Building and
   testing it with no LLM configured produces a working ingestion pipeline you can debug by reading
   rows. Every later phase is debuggable *because* this one is already trustworthy.
2. **Quiz and exercise share one state machine** (module spec §11). Building the quiz properly
   makes the exercise nearly free; building them in parallel produces two state machines that
   diverge in ways only a user finds.
3. **The job surface is a prerequisite, not a polish item.** Indexing is the first thing a user
   does and it takes minutes. A phase that builds indexing without `learning.job` produces a
   product where the first interaction is an unexplained wait.

**The central sequencing decision** is therefore: *deterministic before generative, one state
machine before two, and the job surface before the first long-running job* — not "backend then
frontend", which would leave the whole module unverifiable until the end.

## §2. Phase 0 — prerequisites (not this milestone)

| Prerequisite | Milestone | Blocking what |
|---|---|---|
| Core file/asset service | `M18-files.md` | Source uploads (module spec §5.1) |
| Core LLM service + embeddings + pgvector image | `M19-llm.md` | Everything from Phase 3 onward |

Both are specification-only today. **Do not start Phase 1 until both are merged and green** —
starting earlier means building against two moving interfaces, and the module's own boundary tests
cannot pass while `disp.core.llm` does not exist.

Verify before proceeding: `docker compose exec postgres psql -c 'CREATE EXTENSION vector'` succeeds,
`platform.files` and `platform.llm` both exist on `Platform`, and `FakeLLM` is importable from
`disp.core.llm`.

## §3. Phase 1 — skeleton and schema

Module spec §4, §5, §6, §7, §19.

- `__init__.py` with `get_module()`, `manifest.py`, `config.py`.
- `models.py` — all 22 tables.
- `migrations/` — `env.py` re-export, `script.py.mako`, and a **hand-written** `0001` (raw
  `op.execute` SQL, matching `plants`), including `CREATE EXTENSION IF NOT EXISTS vector`.
- `alembic.ini` gains its `[learning]` section — the only registration step.
- One line each in `tests/conftest.py` and `docker-compose.e2e.yml`'s `migrate` service.
- Course CRUD only: router, service, ACL with the OWNER grant in the creating transaction,
  `readable_ids` list filtering, 404-not-403.

**Verification.** `./dev migrate learning` clean up and down. `./dev test` green, including
`tests/core/test_boundaries.py` and `tests/core/test_plugin_proof.py` — the latter asserting via
`git status` that zero files under `src/disp/core/` changed. That assertion is the whole point of
doing the skeleton first: if it fails here, something in the design needs core and you want to know
now, not in Phase 5.

## §4. Phase 2 — ingestion, parsing only

Module spec §8.1.

- Source upload through `platform.files.put` with an `AcceptSpec` capped at
  `max_source_bytes`; pasted-text sources with no asset.
- Markdown/HTML heading-tree parsing into `source_section` rows with `heading_path` breadcrumbs and
  character offsets; plain-text block coalescing; PDF text extraction into the plain-text path.
- `search_tsv` generated column populated by the DDL, GIN index in place.

**No LLM call exists in this phase.** SRT is accepted and stored but produces no sections yet — it
needs §8.2, which is Phase 3.

**Verification.** Upload a real multi-chapter markdown file and read `source_section` in `./dev
shell`. Heading paths must be correct breadcrumbs and offsets must slice back to the original text.
This is the phase where a bug is cheapest to find and most expensive to miss, because everything
downstream treats these rows as ground truth.

## §5. Phase 3 — indexing, jobs, and the alignment call

Module spec §8.2–§8.5, §16, §17 (first five calls).

Build the job surface **first**, before the task that uses it:

- `learning.job` lifecycle in `service/jobs.py`, the `GET /jobs/{job_id}` route, and the partial
  unique index enforcing one active job per course per kind.
- `@platform.scheduler.task("learning.index_course", queue="learning")` in `register()`, taking
  `job_id` as a JSON-serialisable string and opening its own `session_scope()`.
- Then the phases inside it: SRT segmentation → topic alignment → embedding fallback for unmatched
  sections → tag generation → summaries.

Three ordering rules that are easy to get wrong and hard to debug:

- **Commit the `job` row before deferring the task.** Deferring first races the worker against the
  transaction creating the row it will look up.
- **Write progress in short transactions at phase boundaries**, not inside the long transaction
  holding the topic inserts — otherwise nothing is visible until the whole job commits.
- **Commit `status='failed'` before letting the exception propagate**, so a Procrastinate retry
  can't lose the record. Same ordering as `notifier.py:_deliver_notification`.

Add the `media` volume to the `worker` service in `docker-compose.yml` in this phase (module spec
§16.4). Ingestion runs in the worker and reads uploaded bytes; without the mount it fails **only in
production**, and **only for uploaded rather than pasted sources** — local dev runs the app directly
with a relative media root and never reproduces it.

**Verification.** Index a real three-source course end to end against a live model, then re-index
and confirm module spec §8.5: topics with stable names survive, their `topic_tag_score` history
survives, notes anchored to removed sections become unanchored rather than disappearing, and
`path_item` rows are untouched. Confirm `unmatched_section_ids` is non-empty on at least one
realistic input — if the threshold never rejects anything, it is set too low and the review surface
is decorative.

## §6. Phase 4 — path generation and approval

Module spec §9.

- `learning.generate_path` task on the same queue, same job pattern.
- Draft editing: reorder, retitle, split, merge, delete.
- `POST /path/approve` flipping every item and setting the course `active`.
- The two 409s: `learning.path_not_approved` on session creation over a draft item,
  `learning.path_already_approved` on regenerating over an approved path.

**Verification.** Generate, edit heavily, approve, then attempt to regenerate — the second attempt
must 409 rather than silently discarding curated work.

## §7. Phase 5 — quiz workflow

Module spec §10. **The hardest state machine in the module; get it right and Phase 6 is nearly
free.**

Build in this order: create (draft) → edit → start (freeze) → current → submit → follow-up →
advance → summary. Write the parametrized state-machine test suite *as you go*, structured from the
start to run against both session kinds — retrofitting that parametrization after the exercise flow
exists is how the two diverge.

The four rules that need explicit tests, not just implementation:

- Submitting does not advance (module spec §3.2).
- The question set is frozen once `in_progress` (§3.6).
- Generated `target_tag_ids` outside the item's topics are **dropped, not inserted** (§3.3).
- Completion sets `completion_status='completed'` regardless of score (§3.5), and the mastery EMA
  seeds a first observation at its own value rather than at `alpha × observed` (§15.1).

**Verification.** A full session against a live model, including a deliberately wrong answer,
a follow-up, and a completed session scoring near zero that still marks the item done.

## §8. Phase 6 — exercise workflow

Module spec §11. Reuse `service/sessions.py`. The three differences are `internal_rubric`,
`passed BOOLEAN` instead of a score, and no effect on `completion_status`.

**Verification.** The Phase 5 suite, parametrized, passes for exercises unchanged. Plus the
rubric-leak test: serialize every exercise response model *and the generated OpenAPI schema* and
assert the rubric text appears in neither. Checking one handler's output would pass while a later
`include_in_schema` change leaks it.

## §9. Phase 7 — explain, chat, notes

Module spec §12, §13, §14.

- Explain/guide/summarize — stateless, no session, no score, no completion effect. The simplest
  generative surface; a good place to confirm the LLM facade's error mapping (`503
  learning.llm_unavailable`, `422 learning.llm_refused`) end to end.
- Chat: `path_item` and `custom` scopes first — both deterministic joins. Freeform last, since it is
  the only user-facing read path that retrieves (FTS then pgvector, merged and deduped).
- Notes: the `ck_note_single_anchor` constraint, soft delete, label and anchor filters.

## §10. Phase 8 — mastery, progress, tile, settings, events

Module spec §15, §20, §21, §22. Small, and mostly read paths over data the previous phases wrote.

The tile provider **MUST NOT call the LLM** — the dashboard enforces a 3-second timeout and swaps in
a fallback on any exception, so a tile that summarised progress with a model call would degrade to
the fallback under exactly the load where it matters.

## §11. Phase 9 — web client

Module spec §23. Eight screens, `_app.learning.*.tsx` routes over `-learning*.tsx` screens.

- One line in `components/layout/navItems.ts`'s `MODULE_ROUTES` — without it the module never
  appears in nav no matter what the manifest says.
- `./dev openapi && pnpm api:generate`, with `src/api/generated` committed.
- Job polling in **one** hook, with a `refetchInterval` that stops on a terminal status.
- Any child route's `beforeLoad` that reads a query a parent `loader` populates must
  `ensureQueryData`, never `getQueryData` — the `/settings/$domain` bug in `CLAUDE.md`, and
  `/learning/$courseId/...` is exactly that shape.

**Verification.** `pnpm test` with coverage gates green, `pnpm test:e2e` against the composed stack,
`pnpm api:check` clean.

## §12. Testing

The module spec's §25 is the full list. Three items are worth restating because they are the ones a
build under time pressure drops first:

- **The parametrized quiz/exercise suite** is the single highest-value test in the milestone. A
  divergence between the two workflows must fail a test, not ship.
- **`internal_rubric` absence** must be asserted against serialized output *and* the OpenAPI schema.
- **Job durability** must be asserted from a separate session. Asserting inside the transaction that
  rolled back proves nothing about what a retry would see.

No test may reach a real model or embedding API; `FakeLLM` everywhere, and a test that hits
`api.anthropic.com` is a failed test even when it passes.

Coverage: the global `≥85%` gate. Split `service.py` into the four-file package from the start
(`ingest`, `path`, `sessions`, `chat`, plus `notes`, `mastery`, `jobs`) — this module's service
layer is larger than `plants`' 718 lines and one file will not stay navigable.

## §13. Operations (`docs/operations.md` amendments)

- `pgvector/pgvector:pg16` across the three compose files and `tests/conftest.py` — **a rebuild, not
  a data migration**; existing volumes mount unchanged. Say so plainly, so nobody plans a
  dump/restore window they don't need.
- The `media` volume on `worker` (§5).
- `DISP_LLM_ENABLED` and its key are optional: without them the module installs, courses and sources
  work, and generative routes return `503`. That degradation is deliberate and should be documented
  as supported, not as a broken state.
- Backups: everything except uploaded source bytes is in `pg_dump`, because `raw_text` is a column.
  A database-only restore leaves courses fully usable and loses only re-parsing — note explicitly
  that this is a *better* failure than `plants`' silent `404 modules.plants.no_image`, so an operator knows
  which module fails which way.
- Worker concurrency: `run_worker_async(concurrency=4)` means four simultaneous indexes starve every
  other task in the deployment, including `core.deliver_notification` — which is how a user stops
  being told their previous index finished. Raise it, or give the `learning` queue its own worker
  process, before running more than a couple of courses.

## §14. Out of scope

Spaced repetition and review scheduling; PDF structure recovery; streaming chat and explain;
incremental (non-full) re-indexing; multi-pass or self-consistency grading; mastery time-decay;
classes, cohorts, and instructor views; the Batches API for bulk tag generation; a second settings
panel.

> The single-panel restriction deserves a decision rather than silent omission. It is not a design
> preference — `settings_store._find_panel` returns the first panel whose key prefix matches a
> domain, so a second `learning.*` panel would be unreachable over HTTP. That is a **core defect**
> affecting every future module, and the fix (match on the full panel key rather than the domain
> prefix) is small. Fix it in core rather than designing around it here — but make the call
> explicitly, and if it stays unfixed, record it as a known core limitation rather than as a
> `learning` design choice.

## Dependencies

**`M18` (core files) and `M19` (core LLM) must both be complete.** Beyond those: the module contract
and registry (M3, M10), Alembic branch-per-module (M5), auth and ACL (M6), scheduler (M7), settings
store (M8), notifier (M9), and the test suite (M15). Phase 9 depends on the web client through
`client/M11`.

## Verification

- `./dev test` green; `./dev lint` clean; `tests/core/test_plugin_proof.py` still passing — adding
  this module changed zero files under `src/disp/core/`.
- **Run the built image, don't just build it.** `docker compose up`, upload a real book, index it,
  approve a path, take a quiz to completion, and confirm the mastery score moved. Both of this
  repo's Docker bugs were found by running the image, never by building it (`CLAUDE.md`).
- Boot with `DISP_LLM_ENABLED=false` and confirm courses and sources still work while generative
  routes return `503` — the degraded mode is a supported configuration and needs testing as one.
- Re-index a course that already has mastery history and confirm the scores survive. This is the
  milestone's most consequential behaviour and the only test of it is doing it.
- Index two courses concurrently and confirm the worker still delivers notifications — the
  `concurrency=4` starvation question (§13) answered with evidence rather than assumed.
- Take one quiz question's `internal_rubric` from the database, grep the full OpenAPI dump and a
  captured HTTP response body for it, and find nothing.
