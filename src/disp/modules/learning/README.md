# learning

Point several books, transcripts and articles at one subject; get back a merged topic index, a
tiered learning path, and quizzes and exercises that know what you're bad at.

> **Status: specified, not built.** `TECHNICAL-SPEC.md` in this directory is the complete reference.
> This module depends on two capabilities that are themselves unbuilt — the core file service
> (`milestones/server/M17-files.md`) and the core LLM service (`milestones/server/M18-llm.md`) — and
> `milestones/server/M19-learning.md` sequences the work.

## Model

Twenty-two tables in the `learning` schema. The ones that carry the design:

| Table | Holds |
|---|---|
| `course` | The aggregate root, and the ACL boundary — one grant covers everything under it |
| `source` / `source_section` | One uploaded or pasted document, split into leaf sections by heading |
| `topic` / `topic_source_section` | The merged index. One concept, N sections, across N sources |
| `topic_tag` | The specific skill a question targets and mastery is measured in |
| `path_item` / `path_item_topic` | One ~30-minute lesson, over one or more topics |
| `quiz_session` / `exercise_session` | "Do I know it?" and "Can I do it?", same state machine |
| `topic_tag_score` | One EMA per (tag, user) |
| `note` | Yours. Labelled `note`/`todo`/`question`/`extra`, anchored to one thing or to nothing |
| `job` | Because indexing takes minutes and you need to see it happening |

## The one rule that matters

**Topics are aligned once, at index time. Every runtime read is a plain SQL join.**

```
path_item → path_item_topic → topic → topic_source_section → source_section
```

The alternative is retrieving similar sections per request — which means the same lesson serves
different content on different days as the index grows, and quiz questions drift away from the
material you actually read. Doing the fuzzy work once, up front, where you can review its output,
makes every later read cheap, repeatable, and inspectable.

Semantic search survives in exactly two places, both of them off the common path: resolving a
section the alignment call couldn't confidently place, and freeform course-wide chat.

## Tags are a closed world

Quiz and exercise generation picks `target_tags` from tags that already exist on the topic. It never
invents one, and any tag the model returns that doesn't resolve is discarded rather than inserted.

Mastery is an exponential moving average per tag. If every session coined its own phrasing —
"thread safety", "thread-safety", "concurrency in singletons" — each would start a fresh score and
the whole weak-points surface would be noise. Fixing the vocabulary at indexing time is what makes
*"you've been weak on lazy initialisation for three months"* something the data can actually say.

## Nothing auto-advances

Submit an answer, and the session stays exactly where it is. Advancing is a separate call, allowed
only once the current question is answered.

That's deliberate: the follow-up conversation after a wrong answer is where most of the learning
happens, and a state machine that jumps to the next question on submit throws it away.

## Completion, not score, marks a lesson done

Finish the quiz scoring 40% and the path item is complete — with three tags sitting at the bottom of
your weak-points list. Progress and mastery answer different questions, and conflating them gives
you a progress bar that goes backwards on a bad day.

## Derived state is computed, never stored

Progress percentages, weak-point rankings, session summaries — all queries. Only
`topic_tag_score.rolling_score` is stored, because an EMA is genuinely incremental. Everything else
would be a cache with no invalidation story.

## Surfaces

- **Tile `learning.next_up`** — next uncompleted lesson per active course, plus your two weakest
  skills. Computed per request; no LLM call (the dashboard's 3-second timeout is not negotiable).
- **Jobs** — indexing and path generation return `202` and a job id. `GET /api/learning/jobs/{id}`
  reports phase and progress; a notification fires when indexing finishes. This is the first
  job-status surface in DISP — nothing else in the platform exposes one.
- **Settings panel `learning.study`** — daily reminder toggle, weak-point threshold. Exactly one
  panel, because core only serves the first panel per domain.
- **Chat** — scoped to a lesson, to several lessons, or to the whole course. The first two are
  deterministic joins; only the freeform case retrieves.

## Sources on disk, text in Postgres

Uploaded bytes go through the core file service; the extracted text is a column. So a
database-only restore leaves every course fully usable and only loses the ability to re-parse the
original — a gentler failure than the equivalent in `plants`, and worth knowing which way round it
is.

## Access control

One ACL row per course. Topics, path items, sessions and notes have none of their own — they inherit
it, so sharing a course shares the whole thing. Personal state stays personal: mastery scores, chat
sessions and notes are all keyed by user, so two people studying shared material keep separate
progress. A caller who can't read a course gets 404, never 403.
