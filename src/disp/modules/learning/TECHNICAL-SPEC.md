# `learning` Module — Technical Specification

**Document type:** Prospective specification
**Version:** 1.0
**Status:** Phase 1 (§3 of `M20-learning.md`) implemented — schema, migration, manifest, config, and
course CRUD exist and are tested. Phases 2–9 (everything generative: ingestion, indexing/jobs, path
generation, quiz, exercise, chat/explain, mastery, tile, settings, web client) are specified here but
not yet built.
**Scope:** `src/disp/modules/learning/`, its Alembic branch, its background jobs, and the
`clients/web` screens that consume it

---

## How to read this document

Unlike [`TECHNICAL-SPEC.md`](../../../../TECHNICAL-SPEC.md), which was written **before** the
platform and describes the backbone, and unlike
[`plants/TECHNICAL-SPEC.md`](../plants/TECHNICAL-SPEC.md), which was written **from** a finished
implementation, this document is written **for** an implementation that does not exist yet. It is
normative: an implementing agent must not invent behaviour that is not described here. Where a
requirement seems impossible, contradictory, or unsafe, stop and report the conflict rather than
guessing.

Keywords follow RFC 2119. Where this document and the platform spec disagree, **the platform spec
wins** — this module is a tenant of the contract in §8 of that document, not an amendment to it.

This module depends on two capabilities that are themselves specified but unbuilt:

| Dependency | Spec | Used for |
|---|---|---|
| Core file/asset service | [`docs/milestones/server/M18-files.md`](../../../../docs/milestones/server/M18-files.md) | Storing uploaded source documents (§5.2) |
| Core LLM service | [`docs/milestones/server/M19-llm.md`](../../../../docs/milestones/server/M19-llm.md) | Every generative step (§17), and embeddings (§8.3) |

**Both MUST be implemented before this module.** [`docs/milestones/server/M20-learning.md`](../../../../docs/milestones/server/M20-learning.md)
sequences the build; this document is the reference it builds against. `README.md` in this directory
is the short orientation.

---

## Table of contents

1. [Purpose and non-goals](#1-purpose-and-non-goals)
2. [Domain model](#2-domain-model)
3. [The invariants](#3-the-invariants)
4. [Configuration](#4-configuration)
5. [Schema `learning` — DDL](#5-schema-learning--ddl)
6. [Migrations and branch registration](#6-migrations-and-branch-registration)
7. [Manifest](#7-manifest)
8. [Ingestion and indexing](#8-ingestion-and-indexing)
9. [Learning path generation](#9-learning-path-generation)
10. [Quiz workflow](#10-quiz-workflow)
11. [Practical exercise workflow](#11-practical-exercise-workflow)
12. [Explain, guide, summarize](#12-explain-guide-summarize)
13. [Scoped chat](#13-scoped-chat)
14. [Notes](#14-notes)
15. [Mastery, progress, and weak points](#15-mastery-progress-and-weak-points)
16. [Background jobs and the job surface](#16-background-jobs-and-the-job-surface)
17. [LLM call contracts](#17-llm-call-contracts)
18. [HTTP API](#18-http-api)
19. [Authorization](#19-authorization)
20. [Dashboard tile](#20-dashboard-tile)
21. [Settings panel](#21-settings-panel)
22. [Events](#22-events)
23. [Web client](#23-web-client)
24. [Error code registry](#24-error-code-registry)
25. [Testing](#25-testing)
26. [Operational requirements](#26-operational-requirements)
27. [Known limitations and out of scope](#27-known-limitations-and-out-of-scope)
- [Appendix A — Worked example](#appendix-a--worked-example)
- [Appendix B — Files](#appendix-b--files)

---

## 1. Purpose and non-goals

### 1.1 Purpose

> **"I have five books, a lecture series, and a pile of blog posts on the same subject. Teach me
> it, in order, and tell me what I'm bad at."**

The module ingests heterogeneous source material about one subject, merges it into a single topic
index, generates a tiered learning path over that index, and then drives study through quizzes,
practical exercises, and scoped chat — recording per-skill mastery as it goes.

### 1.2 Goals

- A user **MUST** be able to add several sources of different formats to one course and have them
  merged into a topic index where a topic covered by three books is *one* topic with three sets of
  source sections behind it.
- Every generative step the user acts on — the path, quiz questions, exercise steps — **MUST** be
  staged as an editable draft before it is committed.
- Mastery scores **MUST** stay comparable across sessions months apart, which constrains how skill
  tags are generated (§3.3).
- Runtime reads — lesson content, quiz generation, chat scoping — **MUST** be deterministic joins,
  not live semantic search (§3.1).
- A user **MAY** attach notes to anything, or to nothing, while studying (§14).

### 1.3 Non-goals

- **Not a spaced-repetition system.** There is no review scheduler, no SM-2, no card queue. Mastery
  scores surface weak points; deciding what to do about them is the user's.
- **Not multi-user courseware.** A course belongs to one user and may be shared with specific others
  (§19). There are no classes, cohorts, instructors, or submissions-for-grading.
- **Not a content authoring tool.** Sources come in; the module never edits them.
- **Not a video player.** SRT transcripts are ingested as text with timestamp ranges. Playback,
  seeking, and the media file itself are out of scope.
- **Not a certificate or credential issuer.**

## 2. Domain model

```
                    course (1 user, N sources, N topics, N path_items)
                      │
        ┌─────────────┼─────────────────┬──────────────┬─────────┐
        │             │                 │              │         │
     source        topic             path_item      chat_session note
        │             │  ╲               │  ╲              │
   source_section ────┘   ╲          (M:N join)         chat_message
        │  (M:N join)      ╲              │
        │                topic_tag ───────┴──── quiz_session ── quiz_question ── quiz_answer
        │                    │                                        └─ quiz_followup
        │                    │                 exercise_session ── exercise_step ── exercise_submission
        │                    │                                        └─ exercise_followup
        │                    │
        │              topic_tag_score  (mastery, per user per tag)
        │
   (embedding + tsvector for retrieval only — §8.3, §13.3)
```

| Entity | Answers |
|---|---|
| `course` | "What am I studying?" — the aggregate root, and the ACL boundary (§19) |
| `source` | "Where did this material come from?" — one uploaded or pasted document |
| `source_section` | "Which passage covers this?" — the atom of content, one leaf of a source's heading tree |
| `topic` | "What is this subject made of?" — the merged index; one concept, N sections across N sources |
| `topic_tag` | "Which specific skill is this?" — the unit mastery is measured in |
| `path_item` | "What should I study next, and for how long?" — one ~30-minute lesson |
| `quiz_session` / `exercise_session` | "Do I know it?" / "Can I do it?" |
| `topic_tag_score` | "What am I bad at?" |
| `note` | "What did I want to come back to?" |
| `job` | "Is the thing I started still running?" |

**Why `topic` is not just a heading.** Three books each have a chapter on the Singleton pattern, and
they are not interchangeable — one covers thread safety, one covers testing implications, one is a
paragraph in a broader chapter. Modelling the merge as a first-class entity with an M:N join to
sections (rather than picking a "canonical" source) means a lesson on Singleton draws from all
three, and adding a fourth book later enriches the existing topic instead of creating a duplicate.

**Why mastery attaches to `topic_tag` and not to `topic`.** "You are 62% on Singleton" is not
actionable. "You are weak on *lazy vs eager initialisation* and fine on *thread safety*" is. The tag
is the smallest unit that a generated question can target and a user can act on.

## 3. The invariants

Each of these has a test obligation in §25.

### 3.1 Topics are aligned once, at index time (the central rule)

> **Every runtime read of course content MUST be a deterministic SQL join.** Semantic search MUST
> NOT appear in the path that serves lesson content, quiz generation, exercise generation, explain,
> or path-item-scoped chat.

Gathering the content for a path item is exactly:

```
path_item → path_item_topic → topic → topic_source_section → source_section
```

Rationale: the alternative — embedding the path item's title and retrieving the top-k similar
sections at request time — produces *different content for the same lesson on different days*, as
the index grows or the embedding model changes. Quiz questions would drift out of alignment with
the material the user actually read. Doing the expensive, fuzzy, LLM-and-embedding work **once**, at
ingestion, and reviewing its output (§8.4) means every subsequent read is cheap, repeatable, and
inspectable. Retrieval is confined to two narrow places where non-determinism is acceptable:
resolving an ambiguous section during indexing (§8.3), and freeform course-wide chat (§13.3).

Cost: adding a source requires a re-index (§8.5) rather than being immediately visible. At personal
scale — a handful of sources per course, added in bursts — that is the right trade.

### 3.2 Nothing auto-advances

> **Every state transition in a quiz or exercise session MUST be an explicit client action.**
> Submitting an answer MUST NOT advance to the next question. Answering the last question MUST NOT
> complete the session.

Submit, then optionally follow up, then advance — three separate calls. Rationale: the follow-up
conversation (§10.4) is where most of the learning happens, and a state machine that advances on
submit destroys it. It also makes every transition individually authorizable and individually
testable, and it means a client that crashes mid-question resumes exactly where it was, because
`current_question_index` only ever moves on an explicit request.

### 3.3 Tags are closed-world

> **Quiz and exercise generation MUST select `target_tags` from the owning topics' existing
> `topic_tag` rows.** The generation call MUST NOT create new tags, and any tag the model returns
> that does not match an existing row MUST be discarded, not inserted.

Rationale: mastery is an exponential moving average over a tag (§15.1). If each session invented its
own phrasing — "thread safety", "thread-safety", "concurrency in singletons" — every session would
start a fresh score and the whole mastery surface would be noise. Fixing the vocabulary once, at
indexing time (§8.4), is what makes "you have been weak on lazy initialisation for three months" a
statement the data can support.

The cost is real: a genuinely new sub-skill in later material has nowhere to go until a re-index
regenerates tags. That is the correct direction to fail — a missing tag is visible, a silently
forked one is not.

### 3.4 `internal_rubric` never crosses the API boundary

> **`exercise_step.internal_rubric` MUST NOT appear in any response model, any log line, any error
> `detail`, or any OpenAPI schema.**

It is read server-side only, to grade a submission (§11.3). Rationale: it is the answer key. The
`ExerciseStepOut` Pydantic model simply has no such field — the exclusion is structural, not a
`response_model_exclude` flag that a later refactor can drop. §25 requires a test that asserts the
string is absent from the serialized response of every exercise endpoint.

### 3.5 Completion marks a path item done, not score

> **A path item's `completion_status` becomes `completed` when a quiz session over it reaches
> `completed`, regardless of the score.**

Scoring 40% completes the item and leaves three tags sitting at the bottom of the weak-points list.
Rationale: progress and mastery answer different questions. Conflating them gives a progress bar
that goes backwards when the user has a bad day, which is both demoralising and useless as a measure
of coverage. Completing an *exercise* session does not change `completion_status` — one signal, one
source.

### 3.6 A draft is editable; an in-progress session is not

> **Questions and steps MAY be added, edited, reordered, and deleted while the session's status is
> `draft`. Once status is `in_progress`, the question and step sets are frozen.**

Attempting to mutate them afterwards is `409 learning.session_not_draft`. Rationale: a score
computed over a question set the user edited mid-session means nothing, and `current_question_index`
is an index into an ordered list that must not shift underneath it.

### 3.7 LLM output is validated before it reaches the database

> **Every generative call MUST go through `platform.llm.generate()` with a Pydantic output schema.
> No handler may parse model output by hand, and no unvalidated value may be written.**

Rationale: this is what `M19` §4.1 exists to provide. Beyond validation, the schema is also where
§3.3's tag filtering is enforced — the schema accepts tag *ids*, and ids that do not resolve are
dropped in the service layer before insert.

### 3.8 Due and derived state is computed, never stored

> **Progress percentages, weak-point rankings, and session summaries MUST be computed at read
> time.**

Only `topic_tag_score.rolling_score` is stored, because an EMA is genuinely incremental. Everything
else — "you have completed 7 of 21 items", "your five weakest tags" — is a query. Rationale: the
same reasoning as `plants` §3.3. A stored aggregate is a cache with no invalidation story, and this
module has far more things that would need invalidating.

## 4. Configuration

Module-owned `BaseSettings` in `config.py`, following `plants/config.py` exactly — a module MUST NOT
require a change to core `Settings`, which is `extra="forbid"` (`tests/core/test_plugin_proof.py`).

| Field | Env | Default | Meaning |
|---|---|---|---|
| `max_source_bytes` | `DISP_LEARNING_MAX_SOURCE_BYTES` | `10_485_760` (10 MiB) | Per-source upload ceiling, passed as an `AcceptSpec` override to `platform.files.put` |
| `max_sources_per_course` | `DISP_LEARNING_MAX_SOURCES_PER_COURSE` | `25` | Bounds the alignment call's input (§8.3) |
| `quiz_questions_min` / `_max` | `DISP_LEARNING_QUIZ_QUESTIONS_MIN` / `_MAX` | `5` / `8` | |
| `exercise_steps_min` / `_max` | `DISP_LEARNING_EXERCISE_STEPS_MIN` / `_MAX` | `3` / `6` | |
| `target_item_minutes` | `DISP_LEARNING_TARGET_ITEM_MINUTES` | `30` | The size path generation aims for (§9) |
| `mastery_alpha` | `DISP_LEARNING_MASTERY_ALPHA` | `0.3` | EMA weight on the new observation (§15.1) |
| `alignment_similarity_threshold` | `DISP_LEARNING_ALIGNMENT_SIMILARITY_THRESHOLD` | `0.75` | Cosine floor for the embedding fallback (§8.3) |
| `chat_history_messages` | `DISP_LEARNING_CHAT_HISTORY_MESSAGES` | `20` | Prior turns included in a chat call |

`get_learning_settings()` is `@lru_cache`d; **tests that override these MUST call `cache_clear()`**,
the same trap `plants` documents.

`mastery_alpha` is configurable but the default is load-bearing: at `0.3`, a single bad session
moves a settled score by less than a third, so one distracted evening does not erase a month of
evidence, while five consecutive weak sessions do move it decisively.

## 5. Schema `learning` — DDL

Hand-written raw SQL in `migrations/versions/0001_learning_initial.py`, matching
`plants/migrations/versions/0001_plants_initial.py`'s style. Presented here in dependency order.

### 5.1 Course, sources, sections

```sql
CREATE SCHEMA IF NOT EXISTS learning;
CREATE EXTENSION IF NOT EXISTS vector;   -- requires pgvector/pgvector:pg16 (M19 §7)

CREATE TABLE learning.course (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL,        -- no FK: no cross-schema FKs (platform spec §6.1)
    title       TEXT        NOT NULL,
    description TEXT,
    status      TEXT        NOT NULL DEFAULT 'draft',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ,
    CONSTRAINT ck_course_status CHECK (status IN ('draft','indexing','active','archived')),
    CONSTRAINT ck_course_title_len CHECK (char_length(title) BETWEEN 1 AND 200)
);
CREATE INDEX ix_learning_course_user_created
    ON learning.course (user_id, created_at DESC) WHERE deleted_at IS NULL;

CREATE TABLE learning.source (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id    UUID        NOT NULL REFERENCES learning.course(id) ON DELETE CASCADE,
    title        TEXT        NOT NULL,
    content_type TEXT        NOT NULL,
    file_id      UUID,                       -- core.files id (M18); NULL when pasted rather than uploaded
    raw_text     TEXT        NOT NULL,       -- extracted text; the parse target for §8.1
    token_count  INTEGER     NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_source_content_type
        CHECK (content_type IN ('markdown','html','srt','plain_text','pdf'))
);
CREATE INDEX ix_learning_source_course ON learning.source (course_id, created_at);

CREATE TABLE learning.source_section (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id     UUID        NOT NULL REFERENCES learning.source(id) ON DELETE CASCADE,
    heading_path  TEXT        NOT NULL,      -- "Chapter 4 > Creational > Singleton"
    order_index   INTEGER     NOT NULL,
    start_ref     TEXT,                      -- char offset, or "00:14:02" for srt
    end_ref       TEXT,
    content_text  TEXT        NOT NULL,
    token_count   INTEGER     NOT NULL DEFAULT 0,
    embedding     vector(1024),              -- §8.3; NULL until embedded
    search_tsv    TSVECTOR GENERATED ALWAYS AS
                      (to_tsvector('simple', coalesce(heading_path,'') || ' ' || content_text))
                      STORED,
    CONSTRAINT uq_section_source_order UNIQUE (source_id, order_index)
);
CREATE INDEX ix_learning_section_source ON learning.source_section (source_id, order_index);
CREATE INDEX ix_learning_section_tsv ON learning.source_section USING gin (search_tsv);
CREATE INDEX ix_learning_section_embedding ON learning.source_section
    USING hnsw (embedding vector_cosine_ops);
```

**`source.content_type` is a short label, not a MIME type**, and maps onto `M18`'s `ACCEPT_DOCUMENTS`:

| `source.content_type` | `M18` accept-table entry | Identified by |
|---|---|---|
| `pdf` | `application/pdf` | magic bytes (`%PDF-`) |
| `markdown` | `text/markdown` | UTF-8 decode |
| `html` | `text/html` | UTF-8 decode |
| `plain_text` | `text/plain` | UTF-8 decode |
| `srt` | `application/x-subrip` | UTF-8 decode |

Four of the five have no magic bytes — text formats have no signature by definition — so they are
storable only because `M18` §7.1 gates *inline rendering* on positive identification rather than
gating *acceptance* on it. Every text-family source file is therefore linked with
`Content-Disposition: attachment`, `text/html` included (M18 I6). Do not add a "preview in browser"
affordance that bypasses it.

**Source files are deleted with their source.** `delete_source` calls `files.delete` on `file_id`.
`delete_course` soft-deletes the course, but calls `files.delete` for **every** source file in it in
the same transaction, because a soft-deleted course keeps its source rows forever and their bytes
would otherwise stay stored (and billed) forever (M18 §8.4). Source rows for the column's
pre-M18-v2 values were nulled by the learning revision that renamed `asset_id` → `file_id`.

**`raw_text` is stored in Postgres even when `file_id` is set.** The file is the original bytes for
re-parsing and download; `raw_text` is what every query reads. Keeping both means a database-only
restore leaves the *courses fully functional* and only loses the ability to re-extract — a much
gentler failure than `plants`' `404 modules.plants.no_image`, and one worth stating in `docs/operations.md`.

**`vector(1024)` hardcodes `DISP_EMBEDDING_DIMENSIONS`.** The DDL and the config must agree; `M19`
§7 pins the dimension in settings for exactly this reason. Changing embedding models is a migration,
not a config change — say so in the ops doc.

### 5.2 Topics and tags

```sql
CREATE TABLE learning.topic (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id          UUID        NOT NULL REFERENCES learning.course(id) ON DELETE CASCADE,
    canonical_name     TEXT        NOT NULL,
    description        TEXT,
    aggregated_summary TEXT,                 -- a few sentences; used by lighter calls (§9)
    embedding          vector(1024),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_topic_course_name UNIQUE (course_id, canonical_name)
);

CREATE TABLE learning.topic_source_section (
    topic_id          UUID NOT NULL REFERENCES learning.topic(id) ON DELETE CASCADE,
    source_section_id UUID NOT NULL REFERENCES learning.source_section(id) ON DELETE CASCADE,
    PRIMARY KEY (topic_id, source_section_id)
);
CREATE INDEX ix_learning_tss_section ON learning.topic_source_section (source_section_id);

CREATE TABLE learning.topic_tag (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id   UUID        NOT NULL REFERENCES learning.topic(id) ON DELETE CASCADE,
    name       TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_tag_topic_name UNIQUE (topic_id, name)
);
```

### 5.3 Path

```sql
CREATE TABLE learning.path_item (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id         UUID        NOT NULL REFERENCES learning.course(id) ON DELETE CASCADE,
    tier              TEXT        NOT NULL,
    order_index       INTEGER     NOT NULL,
    title             TEXT        NOT NULL,
    est_minutes       INTEGER     NOT NULL DEFAULT 30,
    status            TEXT        NOT NULL DEFAULT 'draft',
    completion_status TEXT        NOT NULL DEFAULT 'not_started',
    completed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_path_item_tier
        CHECK (tier IN ('concepts','beginner','intermediate','advanced')),
    CONSTRAINT ck_path_item_status CHECK (status IN ('draft','approved')),
    CONSTRAINT ck_path_item_completion
        CHECK (completion_status IN ('not_started','in_progress','completed')),
    CONSTRAINT ck_path_item_completed_at
        CHECK ((completion_status = 'completed') = (completed_at IS NOT NULL))
);
CREATE INDEX ix_learning_path_item_course ON learning.path_item (course_id, order_index);

CREATE TABLE learning.path_item_topic (
    path_item_id UUID NOT NULL REFERENCES learning.path_item(id) ON DELETE CASCADE,
    topic_id     UUID NOT NULL REFERENCES learning.topic(id) ON DELETE CASCADE,
    PRIMARY KEY (path_item_id, topic_id)
);
```

`ck_path_item_completed_at` is a *biconditional*: `completed_at` is set exactly when the item is
completed. A one-directional check would allow the state that breaks §15.2's progress query.

### 5.4 Quiz

```sql
CREATE TABLE learning.quiz_session (
    id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    path_item_id           UUID        NOT NULL REFERENCES learning.path_item(id) ON DELETE CASCADE,
    user_id                UUID        NOT NULL,
    status                 TEXT        NOT NULL DEFAULT 'draft',
    current_question_index INTEGER     NOT NULL DEFAULT 0,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at             TIMESTAMPTZ,
    completed_at           TIMESTAMPTZ,
    CONSTRAINT ck_quiz_session_status CHECK (status IN ('draft','in_progress','completed'))
);
CREATE INDEX ix_learning_quiz_session_item
    ON learning.quiz_session (path_item_id, created_at DESC);

CREATE TABLE learning.quiz_question (
    id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_session_id UUID    NOT NULL REFERENCES learning.quiz_session(id) ON DELETE CASCADE,
    order_index     INTEGER NOT NULL,
    question_text   TEXT    NOT NULL,
    target_tag_ids  UUID[]  NOT NULL DEFAULT '{}',   -- learning.topic_tag ids; §3.3
    status          TEXT    NOT NULL DEFAULT 'pending',
    CONSTRAINT ck_quiz_question_status CHECK (status IN ('pending','answered')),
    CONSTRAINT uq_quiz_question_order UNIQUE (quiz_session_id, order_index)
);

CREATE TABLE learning.quiz_answer (
    id            UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id   UUID             NOT NULL UNIQUE
                                   REFERENCES learning.quiz_question(id) ON DELETE CASCADE,
    answer_text   TEXT             NOT NULL,
    score         DOUBLE PRECISION NOT NULL,
    feedback_text TEXT             NOT NULL,
    tags_tested   UUID[]           NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ      NOT NULL DEFAULT now(),
    CONSTRAINT ck_quiz_answer_score CHECK (score >= 0.0 AND score <= 1.0)
);

CREATE TABLE learning.quiz_followup (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID        NOT NULL REFERENCES learning.quiz_question(id) ON DELETE CASCADE,
    role        TEXT        NOT NULL,
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_quiz_followup_role CHECK (role IN ('user','assistant'))
);
CREATE INDEX ix_learning_quiz_followup_q ON learning.quiz_followup (question_id, created_at);
```

`quiz_answer.question_id` is `UNIQUE` — one answer per question, enforced by the database rather
than by a service-layer check, so a double-submit race resolves as a constraint violation rather
than as two `topic_tag_score` updates for one answer.

`target_tag_ids` is a `UUID[]` and not a join table. Rationale: it is a *snapshot of intent* at
generation time, read as a whole, never queried by tag, and never independently mutated. A join
table would add two tables and buy nothing. `tags_tested` on the answer is the same shape and
deliberately separate — the grader reports what it actually assessed, which may be a subset.

### 5.5 Exercises

Structurally identical to §5.4, with three differences.

```sql
CREATE TABLE learning.exercise_session (   -- columns as quiz_session, plus:
    current_step_index INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE learning.exercise_step (
    id                  UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    exercise_session_id UUID    NOT NULL
                                REFERENCES learning.exercise_session(id) ON DELETE CASCADE,
    order_index         INTEGER NOT NULL,
    instruction_text    TEXT    NOT NULL,   -- shown
    hint_text           TEXT,               -- shown
    internal_rubric     TEXT    NOT NULL,   -- NEVER returned to a client (§3.4)
    target_tag_ids      UUID[]  NOT NULL DEFAULT '{}',
    status              TEXT    NOT NULL DEFAULT 'pending',
    CONSTRAINT ck_exercise_step_status CHECK (status IN ('pending','submitted')),
    CONSTRAINT uq_exercise_step_order UNIQUE (exercise_session_id, order_index)
);

CREATE TABLE learning.exercise_submission (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    step_id         UUID        NOT NULL UNIQUE
                                REFERENCES learning.exercise_step(id) ON DELETE CASCADE,
    submission_text TEXT        NOT NULL,
    passed          BOOLEAN     NOT NULL,
    feedback_text   TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE learning.exercise_followup (  -- as quiz_followup, keyed on step_id
    step_id UUID NOT NULL REFERENCES learning.exercise_step(id) ON DELETE CASCADE
);
```

A submission records `passed BOOLEAN`, not a score. Rationale: a practical exercise either meets its
rubric or it does not; a 0.63 on "implement a thread-safe singleton" would be a number with no
defensible meaning. The mastery update maps it (§15.1).

### 5.6 Chat, notes, mastery, jobs

```sql
CREATE TABLE learning.chat_session (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id  UUID        NOT NULL REFERENCES learning.course(id) ON DELETE CASCADE,
    user_id    UUID        NOT NULL,
    scope_type TEXT        NOT NULL,
    title      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_chat_scope_type CHECK (scope_type IN ('path_item','custom','freeform'))
);

CREATE TABLE learning.chat_session_scope (
    chat_session_id UUID NOT NULL REFERENCES learning.chat_session(id) ON DELETE CASCADE,
    path_item_id    UUID NOT NULL REFERENCES learning.path_item(id) ON DELETE CASCADE,
    PRIMARY KEY (chat_session_id, path_item_id)
);

CREATE TABLE learning.chat_message (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_session_id UUID        NOT NULL REFERENCES learning.chat_session(id) ON DELETE CASCADE,
    role            TEXT        NOT NULL,
    content         TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_chat_message_role CHECK (role IN ('user','assistant'))
);
CREATE INDEX ix_learning_chat_message_session
    ON learning.chat_message (chat_session_id, created_at DESC, id DESC);

CREATE TABLE learning.note (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id         UUID        NOT NULL REFERENCES learning.course(id) ON DELETE CASCADE,
    user_id           UUID        NOT NULL,
    label             TEXT        NOT NULL DEFAULT 'note',
    body              TEXT        NOT NULL,
    -- At most one anchor. All NULL = a general course note (§14).
    path_item_id      UUID        REFERENCES learning.path_item(id) ON DELETE SET NULL,
    topic_id          UUID        REFERENCES learning.topic(id) ON DELETE SET NULL,
    source_section_id UUID        REFERENCES learning.source_section(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at        TIMESTAMPTZ,
    CONSTRAINT ck_note_label CHECK (label IN ('note','todo','question','extra')),
    CONSTRAINT ck_note_body_len CHECK (char_length(body) BETWEEN 1 AND 10000),
    CONSTRAINT ck_note_single_anchor CHECK (
        (path_item_id IS NOT NULL)::int
      + (topic_id IS NOT NULL)::int
      + (source_section_id IS NOT NULL)::int <= 1
    )
);
CREATE INDEX ix_learning_note_course_created
    ON learning.note (course_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX ix_learning_note_path_item
    ON learning.note (path_item_id) WHERE path_item_id IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE learning.topic_tag_score (
    id               UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_tag_id     UUID             NOT NULL REFERENCES learning.topic_tag(id) ON DELETE CASCADE,
    user_id          UUID             NOT NULL,
    rolling_score    DOUBLE PRECISION NOT NULL,
    attempts_count   INTEGER          NOT NULL DEFAULT 0,
    last_practiced_at TIMESTAMPTZ,
    CONSTRAINT uq_tag_score_tag_user UNIQUE (topic_tag_id, user_id),
    CONSTRAINT ck_tag_score_range CHECK (rolling_score >= 0.0 AND rolling_score <= 1.0)
);

CREATE TABLE learning.job (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id        UUID        NOT NULL REFERENCES learning.course(id) ON DELETE CASCADE,
    user_id          UUID        NOT NULL,
    kind             TEXT        NOT NULL,
    status           TEXT        NOT NULL DEFAULT 'queued',
    phase            TEXT,                       -- human-readable current step (§16.2)
    progress_current INTEGER     NOT NULL DEFAULT 0,
    progress_total   INTEGER     NOT NULL DEFAULT 0,
    error_code       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at       TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    CONSTRAINT ck_job_kind CHECK (kind IN ('index_course','generate_path')),
    CONSTRAINT ck_job_status CHECK (status IN ('queued','running','succeeded','failed'))
);
CREATE INDEX ix_learning_job_course ON learning.job (course_id, created_at DESC);
CREATE UNIQUE INDEX uq_learning_job_active ON learning.job (course_id, kind)
    WHERE status IN ('queued','running');
```

`uq_learning_job_active` is a partial unique index and does real work: it makes "one active index
job per course" a database guarantee, so a double-clicked button produces `409
learning.job_already_running` rather than two workers writing the same topic set.

`topic_tag_score` is keyed on `(topic_tag_id, user_id)` even though a course has one owner, because
a course can be shared (§19) and two people studying the same material must not share a mastery
score.

`note` uses `ON DELETE SET NULL` for its anchors while everything else cascades. Rationale: a
re-index (§8.5) rebuilds topics and sections. A note anchored to a section that no longer exists
should become a general course note, not vanish — the user wrote it, and losing it because the
module reorganised its own index would be indefensible.

## 6. Migrations and branch registration

One section in `alembic.ini` — the only registration step:

```ini
[learning]
script_location = src/disp/modules/learning/migrations
version_locations = src/disp/modules/learning/migrations/versions
version_table = alembic_version_learning
version_table_schema = learning
```

`migrations/env.py` is the verbatim re-export used by every module:

```python
# Thin re-export: the real environment lives in disp/core/migrations/env.py so
# every branch shares one implementation (see TECHNICAL-SPEC.md §7.2).
from disp.core.migrations.env import *  # noqa: F403
```

`./dev migrate` and `core/migrations/env.py` are derived and need **no** edit (`CLAUDE.md`). Two
places still enumerate branches by hand and each needs one line:

- `tests/conftest.py` — the alembic upgrade sequence
- `docker-compose.e2e.yml` — the `migrate` service's command chain

`CREATE EXTENSION IF NOT EXISTS vector` lives in this module's `0001`, not in a core migration —
core has no vector column, and a deployment running only `notes` and `plants` should not carry the
extension.

## 7. Manifest

```python
class LearningSettingsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_study_reminder: bool = Field(default=False, title="Daily study reminder", ...)
    weak_point_threshold: float = Field(default=0.5, ge=0.0, le=1.0, title="Weak point threshold",
        description="Tags scoring below this appear in your weak points list.")

MANIFEST = ModuleManifest(
    domain="learning", name="Learning", version="1.0.0",
    description="Merge study sources into one topic index, then learn it with a generated path, "
                "quizzes and exercises.",
    dependencies=(),
    tiles=(TileSpec(key="learning.next_up", title="Learning",
                    description="Your next lesson and weakest skills",
                    size=TileSize.MEDIUM, refresh_seconds=600, order=30),),
    settings_panels=(SettingsPanelSpec(key="learning.study", title="Study preferences",
                    schema_model=LearningSettingsSchema, scope="user"),),
    scheduled_jobs=(ScheduledJobSpec(name="learning.daily_nudge", cron="0 18 * * *",
                    description="Remind users with an in-progress course"),),
    notification_types=(NotificationTypeSpec(key="learning.index_ready",
                        title="Course indexing finished", default_enabled=True),
                        NotificationTypeSpec(key="learning.study_reminder",
                        title="Daily study reminder", default_enabled=False),),
)
```

**Exactly one settings panel.** `settings_store._find_panel` resolves the *first* panel whose key
prefix matches a domain, so a second `learning.*` panel would be unreachable over
`GET|PUT /api/settings/learning`. This is a core limitation, not a design preference — recorded in
§27 as something to fix rather than worked around.

`learning.index_ready` matters more than it looks: indexing is the module's one genuinely long
operation, and it is the only place where a user reasonably walks away and expects to be told.

## 8. Ingestion and indexing

Runs as the `learning.index_course` job (§16). The route returns `202` and a job id; nothing here
happens in a request.

### 8.1 Parse and chunk (no LLM)

| `content_type` | Sectioning |
|---|---|
| `markdown`, `html` | Parse H1–H3 into a tree; each leaf becomes a `source_section` with its heading breadcrumb as `heading_path` and character offsets as `start_ref`/`end_ref` |
| `plain_text` | Blank-line-delimited blocks, coalesced to roughly the target section size; `heading_path` is the source title plus an ordinal |
| `pdf` | Text extraction, then treated as `plain_text`. Structure recovery from PDF layout is out of scope (§27) |
| `srt` | No headings exist. Handled by an LLM call — §8.2 |

This step is deterministic and MUST be independently testable with no LLM configured — it is the
first phase of `M20` for exactly that reason.

### 8.2 SRT segmentation (LLM)

One `learning.segment_transcript` call per source, map-reduced when the transcript exceeds the
call's input budget. Returns `[{label, start_ts, end_ts}]`; each becomes a `source_section` with
`heading_path = label` and the timestamps as `start_ref`/`end_ref`.

Chunking for the map step MUST split on timestamp boundaries and overlap by one caption, so a
concept discussed across a chunk boundary is not sliced in half.

### 8.3 Align sections into topics (LLM, then embeddings)

**One `learning.align_topics` call per course.** The input is the list of
`{source_id, source_title, section_id, heading_path}` across every source — **headings only, never
full text**. Rationale: the full text of 25 sources does not fit in any context window, and does not
need to; the merge decision is a decision about what things are *called*, and headings carry that.

Output: a canonical topic list, each with the member section ids that cover it, plus
`unmatched_section_ids`.

For each unmatched section, the fallback is embedding-based:

1. Embed the section's `content_text` and each candidate topic's `description`.
2. Assign to the highest-cosine topic above `alignment_similarity_threshold`.
3. Below threshold, **leave it unmatched and surface it for review** (§8.4). Do not assign to the
   nearest topic anyway.

That last point is the whole reason the threshold exists. A section forced into a wrong topic is
invisible: it silently corrupts a lesson's content and the quiz generated from it. A section left
unmatched is a visible item on a review list.

### 8.4 Tags and summaries (LLM)

- **One `learning.generate_tags` call per topic**, over that topic's aggregated section text,
  returning 3–6 skill tags. These become the closed world of §3.3, so this call happens once and its
  output is what mastery is measured against for the life of the course.
- **One `learning.summarize_topic` call per topic**, producing `aggregated_summary` — a few
  sentences, used by path generation (§9) so that call's input is summaries rather than full text.

Both are per-topic and independent, which makes them the natural place to use
`settings.llm_fast_model` and, later, the Batches API (§27).

### 8.5 Re-indexing

Adding a source to an already-indexed course requires an explicit re-index — `POST
/api/learning/courses/{id}/index` again. Re-indexing:

- **Preserves** `topic` rows whose `canonical_name` the new alignment also produces, and their
  `topic_tag` rows and `topic_tag_score` history. This is the point: a re-index must not reset the
  user's mastery.
- **Adds** new topics and new tags.
- **Removes** topics no longer produced, cascading their tags and scores.
- **Rewrites** `topic_source_section` wholesale.
- **Leaves `path_item` rows untouched.** The path is a user-approved artifact; regenerating it is a
  separate, explicit action (§9). A re-index that silently rewrote an approved path would discard
  the user's edits.

Notes anchored to deleted topics or sections become general notes (§5.6).

## 9. Learning path generation

Runs as the `learning.generate_path` job.

1. Input: every topic for the course as `{topic_id, canonical_name, aggregated_summary,
   section_count, total_tokens}`. Summaries, not full text (§8.4).
2. One `learning.generate_path` call assigns each topic to a tier and sizes items toward
   `target_item_minutes`, splitting a large topic across two `path_item`s via `path_item_topic`, or
   merging small ones into a single item.
3. Output is written as `path_item` rows with `status='draft'`.
4. The user reorders, merges, splits, retitles, and deletes.
5. `POST /courses/{id}/path/approve` flips every item to `approved` and sets the course to `active`.

**Quiz and exercise sessions MAY only be created over an `approved` path item.** Attempting it on a
draft is `409 learning.path_not_approved`. Rationale: the draft path is scratch space, and mastery
recorded against a lesson the user then deleted would be orphaned data with a score attached.

Regenerating the path over an existing one **discards draft items and leaves approved ones**,
returning `409 learning.path_already_approved` if any approved item exists. Replacing an approved
path is a delete-then-regenerate, made explicit so nobody loses a curated sequence to a misclick.

## 10. Quiz workflow

State machine `draft → in_progress → completed`, driven entirely by explicit actions (§3.2).

| Action | Effect |
|---|---|
| **Create** | Gather content by the §3.1 join. One `learning.generate_quiz` call produces 5–8 questions with `target_tag_ids` drawn from the item's topics' tags (§3.3). Session `status='draft'` |
| **Edit** | Add / edit / delete / reorder questions. `draft` only (§3.6) |
| **Start** | `status='in_progress'`, `current_question_index=0`, `started_at` set. Question set frozen |
| **Current question** | Returns the question at `current_question_index` — text and nothing else |
| **Submit answer** | One `learning.grade_quiz` call against the source content. Writes `quiz_answer` (score, feedback, `tags_tested`); updates `topic_tag_score` for each tag tested (§15.1); question → `answered`. **Does not advance** |
| **Follow up** | Free-form Q&A on the just-graded question, stored in `quiz_followup`. Requires the question to be `answered`. Does not advance |
| **Advance** | Allowed only when the current question is `answered`. Increments the index; past the last question → `status='completed'`, `completed_at` set, and the path item's `completion_status='completed'` (§3.5) |
| **Summary** | `completed` only. Overall score, per-question breakdown, and this session's lowest-scoring tags — all computed (§3.8) |

Submitting an answer to an already-`answered` question is `409 learning.question_answered`.
Advancing past an unanswered question is `409 learning.question_unanswered`.

**Grading input includes the source content**, not just the question. Rationale: the grader must
mark against what the user was asked to read, not against the model's general knowledge — otherwise
a correct-per-the-book answer that the model disagrees with scores badly, and the user has no
recourse.

## 11. Practical exercise workflow

Same state machine and the same action set as §10, with three differences:

1. Each step carries `instruction_text` and `hint_text` that ARE shown, plus `internal_rubric` that
   is **never** returned (§3.4). Grading reads the rubric server-side.
2. Submitting produces `exercise_submission` with `passed BOOLEAN` and feedback, not a score. The
   mastery update maps `passed` to an observation (§15.1).
3. Completing an exercise session **does not** change the path item's `completion_status` (§3.5).

Everything else — draft editing, explicit advance, follow-up-before-advance — is identical, which is
why §25 requires the two workflows' state-machine tests to be parametrized over one shared suite. A
divergence between them should fail a test, not ship.

## 12. Explain, guide, summarize

`POST /api/learning/path-items/{id}/explain` with `mode` in `explain | guide | summarize`.

Stateless. One `learning.explain` call over the path item's aggregated content. Returns markdown. No
session row, no tag updates, no `topic_tag_score` write, no effect on `completion_status`. It is
deliberately the one generative surface that touches no progress state — a user should be able to
re-read an explanation ten times without it meaning anything about their mastery.

## 13. Scoped chat

| `scope_type` | Content assembled from |
|---|---|
| `path_item` | That item's sections, via the §3.1 join |
| `custom` | The union of several user-selected path items' sections |
| `freeform` | Top-k sections retrieved course-wide — §13.3 |

Every message call sends the resolved scope's content plus the last
`chat_history_messages` turns of this session. The scope is fixed at session creation; changing it
means a new session.

### 13.3 Freeform retrieval

Hybrid, in this order:

1. Postgres full-text search over `source_section.search_tsv` (§5.1), the same mechanism `notes`
   already uses.
2. pgvector cosine similarity over `source_section.embedding`.
3. Merge, dedupe by section id, take top-k.

FTS first because it is exact, cheap, and handles the case the user typed a term straight out of the
material. Vector similarity second because it handles the case they did not. This is the **only**
place either mechanism appears on a user-facing read path (§3.1).

## 14. Notes

A note has a `label` (`note` | `todo` | `question` | `extra`), a body, and **at most one** anchor —
a path item, a topic, or a source section — or no anchor at all, in which case it belongs to the
course generally. The single-anchor rule is a database constraint (`ck_note_single_anchor`), not a
service-layer convention.

Rationale for at-most-one rather than several: a note anchored to both a topic and a path item has
no defensible display location, and "which anchor wins" becomes a question every list endpoint has
to answer differently. One anchor, or none.

Notes are soft-deleted (`deleted_at`) and cursor-paginated, filterable by `label` and by anchor.
They participate in no LLM call and affect no score — they are the user's own space, and the module
does not read them.

## 15. Mastery, progress, and weak points

### 15.1 The mastery update

For each tag in `tags_tested`, on every graded answer or submission:

```
observed  = score                     # quiz: the grader's 0.0–1.0
observed  = 1.0 if passed else 0.0    # exercise
new       = (1 - alpha) * old + alpha * observed        # alpha = mastery_alpha, default 0.3
```

A tag with no prior score is seeded at `observed` rather than at `alpha * observed` — otherwise a
first perfect answer would record 0.3, and every tag would start out looking weak.
`attempts_count` increments and `last_practiced_at` is set to now in the deployment timezone
(`get_settings().timezone`, never the server's UTC date — the same rule `plants/service.py:today()`
follows).

The update happens **in the same transaction as the answer write**. A score recorded without its
answer, or an answer without its score, is a state the module cannot repair.

### 15.2 Progress

`GET /courses/{id}/progress` → completed `path_item`s over total approved items, plus a per-tier
breakdown. Only quiz completion counts (§3.5). Computed, never stored (§3.8).

### 15.3 Weak points

`GET /courses/{id}/weak-points` → `topic_tag_score` rows for this user below the settings panel's
`weak_point_threshold`, ordered by `rolling_score` ascending, joined back to their topic and to the
path items that cover that topic, so each weak point is actionable — "practise this" links
somewhere.

Tags with `attempts_count = 0` are excluded. A tag you have never been tested on is not a weakness;
it is an unknown, and mixing the two makes the list useless on day one.

## 16. Background jobs and the job surface

### 16.1 Why this exists at all

**DISP has no job-status mechanism.** All four Procrastinate tasks in the platform
(`core.daily_planner`, `core.deliver_notification`, `plants.daily_check`, `notes.purge_deleted`) are
fire-and-forget; nothing reads `procrastinate_jobs` and no endpoint exposes job state. Indexing a
course is a multi-minute, user-initiated operation whose progress the user must be able to see, so
this module introduces the pattern: a module-owned `learning.job` table, written by the task, read
over HTTP.

It is deliberately module-owned rather than core. Generalising a job-status surface on one
consumer's evidence is how a bad abstraction gets built; if a second module needs it, promote it
then, with two sets of requirements to design against.

### 16.2 The pattern

```python
@platform.scheduler.task("learning.index_course")
async def _index_course(**kwargs: object) -> None:
    job_id = UUID(str(kwargs["job_id"]))  # JSON-serialisable primitives only
    async with session_scope() as session:
        ...
```

- **Enqueue**: the route creates the `job` row (`status='queued'`) and calls
  `platform.scheduler.defer("learning.index_course", job_id=str(job.id))` **after** the row is
  committed — deferring first races the worker against the transaction that creates the row it
  needs.
- **Progress**: the task updates `phase` and `progress_current`/`progress_total` in **its own
  short-lived transaction** at each phase boundary. Writing progress inside the long transaction
  that also holds the topic inserts means nothing is visible until the whole job commits, which
  defeats the purpose.
- **Failure**: `status='failed'` with `error_code` is written **and committed** before the exception
  propagates, so a Procrastinate retry cannot lose the record. This is the commit-then-raise
  ordering `notifier.py:_deliver_notification` already uses.
- **Completion**: `status='succeeded'`, `finished_at` set, then
  `platform.notifier.send(user_id, "learning.index_ready", ...)`.

### 16.3 Queue and concurrency

Both jobs are declared on a dedicated queue (`platform.scheduler.task(..., queue="learning")`).

**The worker runs `concurrency=4`** (`src/disp/worker.py`). An indexing job holds a slot for
minutes, so four concurrent indexes starve every other task in the deployment — including
`core.deliver_notification`, which is how a user stops being told their *previous* index finished.
The deployment note in §26 covers raising concurrency; the partial unique index on `learning.job`
(§5.6) already caps it at one active job per course.

### 16.4 Source bytes are read at upload time only

Text is extracted from an uploaded source inside the upload request and stored as `raw_text`
(§5.1). `create_source` reads the upload once, capped at `max_source_bytes + 1`, extracts from those
bytes, and hands the same bytes to `files.put()`, which still enforces every limit. It never
downloads the file back from the bucket: M18 v2 has no read-back API, by design (M18 §7). The worker's indexing job reads `raw_text`, never the stored file, so the worker needs no
access to the object store for this module. (It has `DISP_FILES_S3_*` anyway, for core's sweeper.)

## 17. LLM call contracts

Every call goes through `platform.llm.generate()` with the named Pydantic schema (§3.7). Schemas
live in `llm_schemas.py`; system prompts are module-level constants in `prompts.py` so they are
cacheable (`M19` §4.3).

| Call name | Input | Output schema | Model tier |
|---|---|---|---|
| `learning.segment_transcript` | Transcript chunk | `TranscriptSegments`: `[{label, start_ts, end_ts}]` | fast |
| `learning.align_topics` | `[{source_id, source_title, section_id, heading_path}]` — headings only | `TopicAlignment`: `topics: [{name, description, member_section_ids}]`, `unmatched_section_ids` | default |
| `learning.generate_tags` | One topic's aggregated text | `TopicTags`: `names: list[str]` (3–6) | fast |
| `learning.summarize_topic` | One topic's aggregated text | `TopicSummary`: `summary: str` | fast |
| `learning.generate_path` | `[{topic_id, canonical_name, aggregated_summary, section_count}]` | `LearningPath`: `[{title, tier, topic_ids, est_minutes}]` | default |
| `learning.generate_quiz` | Item content + available `{tag_id, name}` | `QuizDraft`: `[{question_text, target_tag_ids}]` | default |
| `learning.grade_quiz` | Question, target tags, user answer, source content | `QuizGrade`: `{score, feedback_text, tags_tested}` | default |
| `learning.generate_exercise` | Item content + available tags | `ExerciseDraft`: `[{instruction_text, hint_text, internal_rubric, target_tag_ids}]` | default |
| `learning.grade_exercise` | Instruction, `internal_rubric`, submission | `ExerciseGrade`: `{passed, feedback_text, tags_tested}` | default |
| `learning.chat` | Scope content + history + message | *text* (`generate_text`) | default |
| `learning.explain` | Item content + mode | *text* (`generate_text`) | default |
| `learning.followup` | Question/step + answer + feedback + history | *text* (`generate_text`) | default |

**Tag ids, not tag names, cross the boundary.** Every call that returns tags returns ids drawn from
a list supplied in the same prompt, and the service layer discards any id that does not resolve
against the item's topics. This is how §3.3 is enforced mechanically rather than by asking the model
nicely.

**Grading calls run on the default model.** Grading is judgement work and it is the input to a score
the user will see for months; it is the wrong place to save money. Segmentation, tagging, and
summarisation are closer to extraction and use the fast tier.

## 18. HTTP API

All routes under `/api/learning`, tagged `learning`, mounted automatically by `Registry.wire()`.
Every route declares `response_model`, `status_code`, `summary`, `operation_id`, and a `responses`
dict (platform spec §17.7).

> **Literal path segments MUST be declared above their parameterised siblings.** `/courses/{id}/progress`
> and `/courses/{id}/weak-points` before `/courses/{course_id}`, and `/jobs/{job_id}` in a segment
> that has no sibling `/{other}`. FastAPI matches in declaration order — the identical trap
> `CLAUDE.md` records for `GET /api/plants/due`.

### 18.1 Courses, sources, indexing

| Method | Path | `operation_id` | Notes |
|---|---|---|---|
| GET | `/courses` | `learning_list_courses` | `Page[CourseOut]`, cursor |
| POST | `/courses` | `learning_create_course` | `201` + `Location` |
| GET | `/courses/{course_id}` | `learning_get_course` | |
| PATCH | `/courses/{course_id}` | `learning_update_course` | |
| DELETE | `/courses/{course_id}` | `learning_delete_course` | `204`, soft delete |
| GET | `/courses/{course_id}/progress` | `learning_get_progress` | §15.2 |
| GET | `/courses/{course_id}/weak-points` | `learning_get_weak_points` | §15.3 |
| GET | `/courses/{course_id}/sources` | `learning_list_sources` | |
| POST | `/courses/{course_id}/sources` | `learning_create_source` | Multipart upload or pasted text. `201` |
| DELETE | `/sources/{source_id}` | `learning_delete_source` | `204` |
| POST | `/courses/{course_id}/index` | `learning_index_course` | **`202`** + `JobOut` |
| GET | `/courses/{course_id}/topics` | `learning_list_topics` | Includes `unmatched_section_ids` for review |
| GET | `/jobs/{job_id}` | `learning_get_job` | §16 |

### 18.2 Path

| Method | Path | `operation_id` |
|---|---|---|
| POST | `/courses/{course_id}/path/generate` | `learning_generate_path` (`202` + `JobOut`) |
| GET | `/courses/{course_id}/path` | `learning_get_path` |
| PATCH | `/path-items/{path_item_id}` | `learning_update_path_item` |
| DELETE | `/path-items/{path_item_id}` | `learning_delete_path_item` |
| POST | `/courses/{course_id}/path/approve` | `learning_approve_path` |
| GET | `/path-items/{path_item_id}/content` | `learning_get_path_item_content` |
| POST | `/path-items/{path_item_id}/explain` | `learning_explain_path_item` |

`GET /path` returns the whole ordered list, uncursored. Rationale: it is a bounded set the client
renders as one sequence, and `CursorData` carries only `(ts, id)` — a list whose leading sort key is
`order_index` would need the seek-row re-fetch that `notes` was forced into. The same reasoning
applies to quiz questions and exercise steps.

### 18.3 Quiz and exercise

Identical shapes; `{kind}` is `quizzes` or `exercises`.

| Method | Path | `operation_id` |
|---|---|---|
| POST | `/path-items/{id}/{kind}` | `learning_create_quiz` / `learning_create_exercise` (`201`) |
| GET | `/{kind}/{session_id}` | `learning_get_quiz` / `..._exercise` |
| PATCH | `/{kind}/{session_id}/items/{item_id}` | `..._update_question` / `..._update_step` (draft only) |
| DELETE | `/{kind}/{session_id}/items/{item_id}` | `..._delete_question` / `..._delete_step` |
| POST | `/{kind}/{session_id}/start` | `..._start_quiz` / `..._start_exercise` |
| GET | `/{kind}/{session_id}/current` | `..._get_current_question` / `..._get_current_step` |
| POST | `/{kind}/{session_id}/submit` | `..._submit_answer` / `..._submit_step` |
| POST | `/{kind}/{session_id}/followup` | `..._quiz_followup` / `..._exercise_followup` |
| POST | `/{kind}/{session_id}/advance` | `..._advance_quiz` / `..._advance_exercise` |
| GET | `/{kind}/{session_id}/summary` | `..._quiz_summary` / `..._exercise_summary` |

### 18.4 Chat and notes

| Method | Path | `operation_id` |
|---|---|---|
| POST | `/courses/{course_id}/chats` | `learning_create_chat` |
| GET | `/courses/{course_id}/chats` | `learning_list_chats` |
| GET | `/chats/{chat_id}/messages` | `learning_list_chat_messages` (cursor) |
| POST | `/chats/{chat_id}/messages` | `learning_send_chat_message` |
| GET | `/courses/{course_id}/notes` | `learning_list_notes` (cursor; `?label=`, `?path_item_id=`) |
| POST | `/courses/{course_id}/notes` | `learning_create_note` (`201`) |
| PATCH | `/notes/{note_id}` | `learning_update_note` |
| DELETE | `/notes/{note_id}` | `learning_delete_note` (`204`) |

## 19. Authorization

`RESOURCE_TYPE = "learning.course"`. **One ACL row per course**; every child entity inherits it,
exactly as `plants` intervals and logs inherit their plant's grant.

- `create_course` grants `Permission.OWNER` to the creator **in the same transaction** as the
  insert (platform spec §11).
- `list_courses` filters via `readable_ids(session, user_id=..., resource_type=RESOURCE_TYPE)` —
  never an N+1 of per-row `can()` checks.
- Every other handler resolves its entity up to its course and authorizes against that. A helper
  `_authorize(session, user, course_id, action)` implements resolve-then-require with existence
  hidden: a caller who cannot read the course gets **404, never 403**; `403 core.acl.forbidden` is
  reserved for a caller who can read it but lacks the specific permission.

**Actions come from the closed `ACTION_REQUIRES` vocabulary** — `read`, `list`, `create`, `update`,
`delete`, `share`, `unshare`, `transfer`. Anything else raises `ValueError` inside core. So:

| Operation | Action |
|---|---|
| Read content, list a path, get a summary | `read` |
| Index, generate a path, approve, create a session, submit, advance, write a note | `update` |
| Delete a course, source, note, or path item | `delete` |

Do not invent `grade` or `approve` actions. Admins get no implicit access.

Personal writes are scoped by user, not only by course: `topic_tag_score` is keyed on
`(topic_tag_id, user_id)`, and `chat_session` and `note` carry `user_id`. Two people sharing a course
share the *material* and keep their own progress, conversations, and notes.

## 20. Dashboard tile

`learning.next_up`, `TileSize.MEDIUM`, refresh 600s.

| Field | Value |
|---|---|
| `count` | Approved path items not yet completed, across active courses |
| `items` | The next uncompleted item per active course (max 3), then the two weakest tags, each with `href` |
| `empty_text` | `"No active courses"` |

Computed per request from `ctx.session` / `ctx.user` (§3.8). The dashboard enforces a **3-second
timeout** and substitutes a fallback tile on any exception, so the provider MUST NOT make an LLM
call — a constraint worth stating because "summarise my progress" is a tempting tile.

## 21. Settings panel

`learning.study`, user scope. Two fields, per §7. Read back with the
`plants/reminders.py:_preferences()` idiom — `platform.store.get(...)` per field with the schema
class's defaults, then a defensive re-validate that falls back to defaults on `ValueError` rather
than letting one hand-edited row abort a sweep.

## 22. Events

```python
@dataclass(frozen=True, slots=True)
class CourseIndexed:
    course_id: UUID
    user_id: UUID
    topic_count: int
    unmatched_count: int


@dataclass(frozen=True, slots=True)
class PathItemCompleted:
    course_id: UUID
    path_item_id: UUID
    user_id: UUID
    score: float


@dataclass(frozen=True, slots=True)
class MasteryUpdated:
    course_id: UUID
    user_id: UUID
    topic_tag_id: UUID
    old_score: float
    new_score: float
```

Published with `publish_after_commit(session, event)`, subscribed in `register(platform)`.

## 23. Web client

Routes follow the `_app.` / `-` convention: `_app.learning.*.tsx` are thin route files, `-learning*.tsx`
are the screens.

| Route | Screen file | Purpose |
|---|---|---|
| `/learning` | `-learning.tsx` | Course list, create |
| `/learning/$courseId` | `-course-detail.tsx` | Sources, index status, topic review, progress |
| `/learning/$courseId/path` | `-learning-path.tsx` | Draft editing, reorder, approve |
| `/learning/$courseId/items/$itemId` | `-path-item.tsx` | Content, explain, start quiz/exercise, notes |
| `/learning/$courseId/quiz/$sessionId` | `-quiz-session.tsx` | The §10 state machine |
| `/learning/$courseId/exercise/$sessionId` | `-exercise-session.tsx` | The §11 state machine |
| `/learning/$courseId/chat` | `-learning-chat.tsx` | Scoped chat |
| `/learning/$courseId/notes` | `-learning-notes.tsx` | Notes, filtered by label |

Also required:

- **One line in `clients/web/src/components/layout/navItems.ts`** — `MODULE_ROUTES` is a hardcoded
  map intersected with the manifest's domains. A module absent from it never appears in nav even
  though `GET /api/dashboard/manifest` lists it.
- Query keys in `api/queryKeys.ts`, all under a `['learning']` prefix so one invalidation sweeps the
  module; read factories in `api/queries.ts`; mutations in
  `components/learning/useLearningMutations.ts`.
- `./dev openapi && pnpm api:generate`, with `src/api/generated` **committed** (a clean checkout
  builds with no backend, and `pnpm api:check` fails on a diff).
- **Job polling.** After a `202`, poll `GET /jobs/{id}` with a TanStack Query `refetchInterval` that
  stops on a terminal status. This is the client's only polling loop; keep it in one hook.
- **Any `beforeLoad` that reads a query a parent `loader` populates MUST `ensureQueryData`, not
  `getQueryData`** — the `/settings/$domain` bug recorded in `CLAUDE.md`. `/learning/$courseId/...`
  children validating a course id against a parent-loaded list are exactly this shape.
- UI follows `docs/design-system/`, translated into this repo's Tailwind + Radix conventions rather
  than copied — read that directory's "Caveats" first.

## 24. Error code registry

| Code | Status | Raised when |
|---|---|---|
| `learning.not_found` | 404 | Course, or any child, absent or unreadable |
| `learning.source_not_found` | 404 | |
| `learning.path_item_not_found` | 404 | |
| `learning.session_not_found` | 404 | |
| `learning.note_not_found` | 404 | |
| `learning.job_not_found` | 404 | |
| `learning.job_already_running` | 409 | An `index_course`/`generate_path` job is active for the course |
| `learning.not_indexed` | 409 | Path generation before indexing succeeded |
| `learning.path_not_approved` | 409 | Session creation over a draft path item |
| `learning.path_already_approved` | 409 | Regenerating over an approved path |
| `learning.session_not_draft` | 409 | Editing questions/steps after `start` |
| `learning.session_not_started` | 409 | Submit/advance on a `draft` session |
| `learning.session_completed` | 409 | Any mutation on a `completed` session |
| `learning.question_answered` | 409 | Re-submitting an answered question |
| `learning.question_unanswered` | 409 | Advancing past an unanswered question |
| `learning.source_limit` | 409 | `max_sources_per_course` exceeded |
| `learning.unsupported_content_type` | 415 | |
| `learning.empty_source` | 400 | |
| `learning.invalid_note_anchor` | 400 | More than one anchor supplied |
| `learning.llm_unavailable` | 503 | `LLMUnavailable` from the facade |
| `learning.llm_refused` | 422 | `LLMRefused` — surfaced, not retried |

**`core.files.*` and `core.llm.*` codes are surfaced unchanged.** A file that is too large returns
`413 core.files.too_large`, not a re-coded `learning.source_too_large`, so a client handles "file
too large" once rather than once per domain (`M18` §7). The two `learning.llm_*` codes above are the
deliberate exception: they translate an *internal service* failure into a *domain* outcome the user
can act on, and neither has a `core.*` equivalent a client could key on.

Cross-cutting codes (`core.acl.forbidden`, `core.pagination.invalid_cursor`, `core.platform.validation_error`) keep their own
prefixes. Modules raise `AppError`, never `HTTPException`.

## 25. Testing

Real Postgres 16 (now `pgvector/pgvector:pg16`) via testcontainers; per-test rollback; `FakeLLM`
(`M19` §9) everywhere. **No test may reach a real model or embedding API.**

- **Parse-only ingestion tests run with no LLM configured** — §8.1 is deterministic, and proving it
  in isolation is what makes the rest debuggable.
- **One parametrized state-machine suite over quiz and exercise.** They share a state machine (§11);
  a divergence must fail a test. This is the highest-value test in the module.
- **`internal_rubric` absence (§3.4).** Serialize every exercise response model and assert the
  rubric string is absent — including from the generated OpenAPI schema. Asserting only that the
  field is missing from one handler's output would pass while a future `include_in_schema` change
  leaks it.
- **Tag closed-world (§3.3).** A `FakeLLM` returning a tag id belonging to another course must
  produce a question with that id **dropped**, not inserted. Asserting only the happy path proves
  nothing about the rule.
- **No auto-advance (§3.2).** After a submit, `current_question_index` is unchanged and the session
  is still `in_progress`.
- **Completion, not score (§3.5).** A session completed with every answer scoring 0.0 still sets
  `completion_status='completed'`.
- **Mastery seeding (§15.1).** A first observation of 1.0 stores 1.0, not `alpha`.
- **Re-index preserves mastery (§8.5).** Score a tag, re-index with a `FakeLLM` returning the same
  topic names, assert the score survives; assert a note anchored to a removed section becomes
  anchored to nothing rather than disappearing.
- **Job durability (§16.2).** A task that raises leaves a committed `failed` row — asserted from a
  **separate session**, since asserting inside the rolled-back transaction proves nothing.
- **Job uniqueness.** Two concurrent index requests produce one job and one `409`.
- **Route ordering.** `GET /courses/{id}/progress` resolves to the progress handler, and
  `GET /jobs/{id}` is not shadowed.
- **Boundaries.** `tests/core/test_boundaries.py` passes: no import of another module, of
  `disp.core.app`, of `disp.core.llm.client`, or of anything outside the allowed `db`/`auth` names.
- **Plug-in proof.** `tests/core/test_plugin_proof.py` still passes — adding this module changes
  zero files under `src/disp/core/`. Note this holds only because `M18` and `M19` land first; those
  milestones own the core edits.
- **Config shape.** At least one test uses the *shipped default* of every path-like setting, per the
  lesson `plants` §19.4 records — behaviour that depends on a config's shape must be tested at that
  shape, not at a convenient one.

Coverage: the global `≥85%` gate applies. `service.py` will be large; split it (`service/ingest.py`,
`service/path.py`, `service/sessions.py`, `service/chat.py`) rather than letting one 2,000-line
module accumulate.

## 26. Operational requirements

- **`pgvector/pgvector:pg16`** in `docker-compose.yml`, `.test.yml`, `.e2e.yml`, and
  `tests/conftest.py`. A rebuild, not a data migration — existing volumes mount unchanged.
- **`DISP_LLM_ENABLED=true` and a key are required** for anything past §8.1. With the key absent the
  module still installs, courses and sources still work, and generative routes return
  `503 learning.llm_unavailable`. That degradation is deliberate: a deployment that has not decided
  about AI should not be blocked from running the platform.
- **Worker concurrency.** Consider raising `concurrency` above 4 in `src/disp/worker.py`, or give
  the `learning` queue its own worker process, before running more than a couple of courses (§16.3).
- **Backups.** Everything except uploaded source bytes is in `pg_dump`, because `raw_text` is a
  column (§5.1). Source files live in the M18 object store (R2), which is not versioned. A database-only
  restore leaves courses fully usable and only loses re-parsing — state this in `docs/operations.md`,
  because it is a *better* failure than `plants`' and operators should know which is which.
- **Cost.** Indexing a large course is the module's expensive operation. `GET /api/admin/llm/usage`
  (`M19` §11) grouped by `call_name` shows where it goes.

## 27. Known limitations and out of scope

| Limitation | Why it is acceptable / what it would take |
|---|---|
| Adding a source requires an explicit re-index | Direct consequence of §3.1. Incremental alignment — placing new sections against an existing topic list without re-running the whole merge — is a real feature and is additive: the alignment call already returns `unmatched_section_ids`, which is the hook |
| One settings panel only | `settings_store._find_panel` returns the first panel matching a domain prefix. This is a **core defect**, not a design choice here — fixing it (match on the full panel key, not the domain) is a small core change that unblocks every module, and should be done rather than designed around |
| No spaced repetition | §1.3. Weak points identify what to practise; nothing schedules it. A scheduler would need a review-queue entity and a retention model — a feature, not an increment |
| PDF structure is not recovered | Extracted as flat text (§8.1). Heading recovery from PDF layout is a research problem with poor worst-case behaviour; the flat-text path degrades predictably |
| No streaming for chat or explain | No `StreamingResponse` exists anywhere in `src/` (`M19` §14). These are the two places where the wait is most visible; the generated client already ships unused SSE support, so the client half is free when the backend half is built |
| `phase` is a free-text string | A `job` phase enum would be more typable and less useful — the phases differ per job kind and will change as ingestion evolves. The client renders it, it does not branch on it |
| No targeted weak-point practice | The origin draft sketched an optional `POST /path-items/{id}/practice-weak` that would generate questions deliberately aimed at the item's lowest-scoring tags instead of sampling uniformly. Deliberately deferred: it is a *third* generation path over the same state machine, and it needs mastery data that does not exist until the module has been used for a while. Additive when the time comes — the only new behaviour is weighting tag selection in the §17 `learning.generate_quiz` prompt, and §15.3 already computes the ranking it would weight by |
| Grading is single-pass | No self-consistency, no second-opinion pass. Adding one doubles cost for an unmeasured accuracy gain; measure first |
| A course belongs to one user | Sharing via ACL grants exists (§19). Classes, cohorts, and instructor views are §1.3 |
| Mastery has no decay | A tag scored months ago reads the same as one scored yesterday. `last_practiced_at` is stored, so time-decay is a read-time formula change, not a schema change — deliberately left out until there is evidence about the right half-life |

---

## Appendix A — Worked example

A user adds two markdown books and one lecture transcript to a course on design patterns.

**1. Index** — `POST /api/learning/courses/{id}/index` → `202`:

```json
{ "id": "3f9a…", "kind": "index_course", "status": "queued",
  "phase": null, "progress_current": 0, "progress_total": 0 }
```

Polling `GET /api/learning/jobs/3f9a…` walks through
`parsing sources (2/3)` → `aligning topics` → `generating tags (14/22)` → `succeeded`. The user
gets a `learning.index_ready` notification.

**2. Review** — `GET /courses/{id}/topics` shows 22 topics. One is:

```json
{ "id": "a1…", "canonical_name": "Singleton",
  "aggregated_summary": "A creational pattern ensuring one instance…",
  "section_count": 4,
  "tags": [ {"id": "t1…", "name": "lazy vs eager initialisation"},
            {"id": "t2…", "name": "thread safety"},
            {"id": "t3…", "name": "testability and global state"} ] }
```

Four sections: two from book A (chapter body and a worked example), one from book B, one lecture
segment `00:41:10–00:52:33`. Three sections elsewhere came back unmatched and are listed for manual
review rather than guessed into a topic (§8.3).

**3. Path** — generated as draft, 21 items across four tiers. Singleton lands in
`intermediate`, merged with "Monostate" into one 30-minute item. The user splits it back into two,
retitles one, and approves.

**4. Quiz** — `POST /path-items/{id}/quizzes` → 6 draft questions. After `start`, submitting an
answer to question 1:

```json
{ "score": 0.4,
  "feedback_text": "You described the eager form correctly, but the question asked what changes
                    under lazy initialisation in a multithreaded context…",
  "tags_tested": ["t1…", "t2…"] }
```

Mastery moves, with `alpha = 0.3`:

```
t1  (no prior)  → seeded at 0.4
t2  0.80        → 0.7 × 0.80 + 0.3 × 0.4 = 0.68
```

The session stays on question 1 (§3.2). The user asks a follow-up, gets an explanation, *then*
advances.

**5. Completion** — after question 6, `advance` completes the session, sets the path item's
`completion_status='completed'` and `completed_at`, and publishes `PathItemCompleted`. Overall score
0.61 — the item is done regardless (§3.5), and `t1` sits near the top of the weak-points list with
`attempts_count = 1`.

## Appendix B — Files

| File | Contains |
|---|---|
| `__init__.py` | `LearningModule`, `get_module()`, task registration, event subscriptions (§16, §22) |
| `manifest.py` | `MANIFEST`, `LearningSettingsSchema` (§7) |
| `config.py` | `LearningSettings`, `get_learning_settings()` (§4) |
| `models.py` | SQLAlchemy models for §5 |
| `schemas.py` | Pydantic wire models. **No `internal_rubric` field anywhere** (§3.4) |
| `llm_schemas.py` | The output schemas of §17 |
| `prompts.py` | System prompts as module-level constants — cacheable (`M19` §4.3) |
| `service/ingest.py` | §8 parse, align, tag, summarize, re-index |
| `service/path.py` | §9 generation, editing, approval |
| `service/sessions.py` | §10, §11 — the shared state machine |
| `service/chat.py` | §13 chat, §12 explain, §13.3 retrieval |
| `service/notes.py` | §14 |
| `service/mastery.py` | §15 |
| `service/jobs.py` | §16 job row lifecycle |
| `router.py` | §18. Thin: parse → service → return |
| `tiles.py` | §20 |
| `events.py` | §22 |
| `migrations/` | `env.py` re-export, `script.py.mako`, `0001_learning_initial.py` (§5, §6) |
| `README.md` | Short orientation |
| `TECHNICAL-SPEC.md` | This document |
