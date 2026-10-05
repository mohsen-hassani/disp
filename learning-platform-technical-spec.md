# Learning platform module — technical spec

Scope: the specific data model, workflows, and generation contracts this module needs. Auth, module registration/routing conventions, job queue choice, embedding provider, and general code layout are left to whatever the rest of the monolith already does.

## Design principles

- Topics are pre-aligned across sources once, at indexing time. Runtime reads (lesson content, quiz/exercise generation, explain, scoped chat) are plain DB joins — no live semantic search in the common path.
- Embeddings (pgvector) are used only in two narrow, optional spots: (a) resolving a source section to a topic when heading-based matching is ambiguous during indexing, and (b) freeform, course-wide chat that isn't scoped to a specific path item.
- Every generative step the user acts on (path, quiz questions, exercise steps) is staged as a draft the user can review/edit before it's committed.

## 1. Data model

**Sources & sections**
- `sources`: id, title, content_type (`markdown` | `html` | `srt` | `plain_text`), raw_text (or a reference to wherever the app already stores uploaded files), created_at
- `source_sections`: id, source_id (FK), heading_path (e.g. "Chapter 4 > Singleton"), order_index, start_ref/end_ref (char offsets, or timestamp range for SRT), content_text, token_count

**Topics — the merged index**
- `topics`: id, course_id (FK), canonical_name, description, aggregated_summary (short, LLM-written — used for lighter calls like path generation)
- `topic_sources` (join): topic_id (FK), source_section_id (FK)
- `topic_tags`: id, topic_id (FK), name — candidate skill/sub-concept tags generated once at indexing time (e.g. under "Singleton": "lazy vs eager init", "thread safety"). Quiz and exercise generation must pick from this list rather than inventing new tags per session, so mastery scores stay comparable across sessions over time.

**Courses & path**
- `courses`: id, title, status, created_at
- `path_items`: id, course_id (FK), tier (`concepts` | `beginner` | `intermediate` | `advanced`), order_index, title, est_minutes, status (`draft` | `approved`), completion_status (`not_started` | `in_progress` | `completed`)
- `path_item_topics` (join, many-to-many — handles a topic split across two items, or two topics merged into one): path_item_id (FK), topic_id (FK)

**Quiz**
- `quiz_sessions`: id, path_item_id (FK), status (`draft` | `in_progress` | `completed`), current_question_index, created_at, completed_at
- `quiz_questions`: id, quiz_session_id (FK), order_index, question_text, target_tags (array of topic_tag ids), status (`pending` | `answered`)
- `quiz_answers`: id, question_id (FK), answer_text, score (float 0.0–1.0), feedback_text, tags_tested (array)
- `quiz_question_followups`: id, question_id (FK), role (`user` | `assistant`), content, created_at

**Practical exercises — same shape as quiz**
- `exercise_sessions`: id, path_item_id (FK), status, current_step_index, created_at, completed_at
- `exercise_steps`: id, exercise_session_id (FK), order_index, instruction_text, hint_text, internal_rubric (never sent to the client), status (`pending` | `submitted`)
- `exercise_submissions`: id, step_id (FK), submission_text, passed (bool), feedback_text
- `exercise_step_followups`: same shape as `quiz_question_followups`

**Chat**
- `chat_sessions`: id, scope_type (`path_item` | `custom` | `freeform`), created_at
- `chat_session_scopes` (join, used when scope_type is `path_item` or `custom`): chat_session_id (FK), path_item_id (FK)
- `chat_messages`: id, chat_session_id (FK), role (`user` | `assistant`), content, created_at

**Mastery / weak points**
- `topic_tag_scores`: id, topic_tag_id (FK), rolling_score (float — e.g. EMA: `new = 0.7*old + 0.3*observed`), attempts_count, last_practiced_at

## 2. Ingestion & indexing ("analyze and index my sources")

1. **Parse & chunk each source.**
   - `markdown` / `html` / `plain_text`: parse headings (H1–H3) into a section tree; each leaf becomes a `source_section` with its heading breadcrumb and text.
   - `srt`: one LLM call over the transcript (map-reduced if it exceeds your context budget) returning topic-labeled timestamp ranges — there are no headings to parse mechanically.
2. **Align sections into topics.** One LLM call per course: input is the list of `{source_id, heading_path}` (or SRT labels) across every source — headings only, not full text. Output: a canonical topic list, each with the member section IDs that cover it.
   - Any section the model can't confidently place: fall back to embedding the section's text plus each candidate topic's description, and assign by cosine similarity above a threshold. Below threshold, leave unmatched and surface it for manual review rather than guessing.
3. **Generate topic tags.** One LLM call per topic, using its aggregated source text: produce 3–6 candidate skill tags (`topic_tags`) that quiz/exercise generation will draw from later.
4. **Write an `aggregated_summary`** per topic (a few sentences) for lighter-weight calls like path generation.

## 3. Learning path generation ("give me a learning path")

1. Input: every topic for the course (canonical_name + aggregated_summary + rough source length).
2. One LLM call: assign each topic to a tier, and size items to ~30 minutes — splitting a topic across two `path_items` (via `path_item_topics`) if its material is too large, or merging small topics into one item.
3. Output written as `path_items` with status=`draft`. Surface for user edits (reorder, merge, split, retitle, delete).
4. An explicit "approve path" action flips every item's status to `approved`.

## 4. Quiz workflow ("quiz me on [path item]")

State machine: `draft → in_progress → completed`, driven entirely by explicit actions — nothing auto-advances.

| Action | Effect |
|---|---|
| Create quiz | Gather content transitively: `path_item → path_item_topics → topics → topic_sources → source_sections`. One LLM call generates 5–8 `quiz_questions` (text + target_tags drawn from the item's topic_tags). Session status=`draft`. |
| Edit questions | User can edit/delete/add questions while status=`draft`. |
| Start | Status→`in_progress`, current_question_index=0. |
| Get current question | Returns the question at current_question_index — text only, never the answer. |
| Submit answer | LLM grades against the source content: writes `quiz_answers` (score, feedback, tags_tested); updates `topic_tag_scores` for each tag tested. Question status→`answered`. |
| Follow-up | Free-form Q&A on the just-graded question, stored in `quiz_question_followups`. Does not advance the session. |
| Advance | Only allowed once the current question is `answered`. Increments current_question_index; past the last question, status→`completed`, `completed_at` set, and the path item's `completion_status`→`completed` — quiz completion is what marks a path item done, regardless of score. |
| Summary | Once completed: overall score, per-question breakdown, and this session's lowest-scoring tags. |

## 5. Practical exercise workflow ("give me a practical exercise on [path item]")

Same state machine and action set as the quiz (draft → in_progress → completed, explicit advance), with these differences:
- Each `exercise_step` carries `instruction_text` and `hint_text` that ARE shown, plus an `internal_rubric` that is never returned to the client — used server-side only, to grade the submission.
- Submitting a step produces an `exercise_submissions` row (passed/feedback) instead of a numeric score; still updates `topic_tag_scores` via the step's associated tags.
- Same follow-up-before-advance pattern as the quiz.

## 6. Topic-scoped chat

- `scope_type = path_item`: content = the path item's aggregated source sections (deterministic join, same as quiz/exercise).
- `scope_type = custom`: user selects several path items up front; content = union of their sections.
- `scope_type = freeform`: not tied to specific path items — retrieve top-k `source_sections` via Postgres full-text search (`tsvector`/GIN index) over the course. Add pgvector similarity only if FTS recall proves too weak in practice. Treat as an optional, later addition — not required for v1.
- Every message call: context = the resolved scope's aggregated content + this session's prior `chat_messages`.

## 7. Explain / guide / teach / summarize

Stateless, single call — e.g. `POST /path-items/{id}/explain?mode=explain|guide|summarize`. Input = the path item's aggregated content. Output = markdown. No session, no tag/score updates, no completion effect — this command doesn't touch progress tracking.

## 8. Weak points & progress

- `GET /courses/{id}/progress` → completed `path_items` / total, for overall % (only quiz completion counts, per section 4).
- `GET /courses/{id}/weak-points` → `topic_tag_scores` sorted ascending by rolling_score, joined back to their topic/path item for display.
- Optional (phase 2): `POST /path-items/{id}/practice-weak` — generates quiz questions or exercise steps that deliberately target this path item's lowest-scoring tags instead of sampling the topic uniformly.

## 9. LLM call contracts

| Call | Input | Output |
|---|---|---|
| SRT segmentation | transcript text (chunked if needed) | `[{label, start_ts, end_ts}]` |
| Topic alignment | `[{source_id, heading_path}]` across all sources | `[{topic_name, description, member_section_ids}]` + `unmatched_section_ids` |
| Topic tag generation | topic's aggregated text | `[tag_name]` (3–6) |
| Path generation | `[{topic_id, canonical_name, aggregated_summary}]` | `[{path_item_title, tier, topic_ids[], est_minutes}]` |
| Quiz question generation | path item's aggregated content + its topic_tags | `[{question_text, target_tags[]}]` |
| Quiz grading | question_text, target_tags, user answer, source content | `{score, feedback_text, tags_tested[]}` |
| Exercise step generation | path item's aggregated content | `[{instruction_text, hint_text, internal_rubric}]` |
| Exercise grading | instruction, internal_rubric, submission | `{passed, feedback_text}` |
| Chat turn | scope's aggregated content + message history | assistant reply text |
| Explain/guide/summarize | path item's aggregated content, mode | markdown text |

## 10. Suggested build order

1. Data model + ingestion/chunking (parsing only — no LLM calls yet).
2. Topic alignment + tags (first LLM-dependent piece).
3. Path generation + approval flow.
4. Quiz workflow end-to-end (it exercises the hardest state machine — get this right and the exercise flow is nearly free).
5. Exercise workflow.
6. Explain/guide/summarize (simplest, stateless).
7. Weak points + progress views.
8. Scoped chat; freeform chat + FTS/pgvector as a later addition.
