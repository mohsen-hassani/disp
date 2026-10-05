"""§8.1: deterministic parsing (no LLM, no DB) plus the source CRUD that
uses it. The parsers (`parse_source`, `parse_srt_captions`, `_extract_pdf_text`)
are pure functions precisely so this phase is testable with nothing
configured — the first phase of `M20` for exactly that reason.
"""

import io
import re
from dataclasses import dataclass
from datetime import timedelta
from html.parser import HTMLParser
from typing import TYPE_CHECKING, cast
from uuid import UUID

import srt as srt_lib
import structlog
from fastapi import UploadFile
from pypdf import PdfReader
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser
from disp.core.config import get_settings
from disp.core.db import session_scope
from disp.core.errors import AppError
from disp.core.events import publish_after_commit
from disp.core.files import AcceptSpec, FileStore
from disp.core.llm import LLMCall, LLMNotConfigured, LLMRefused, LLMUnavailable
from disp.modules.learning import llm_schemas, prompts
from disp.modules.learning.config import get_learning_settings
from disp.modules.learning.events import CourseIndexed
from disp.modules.learning.models import (
    Course,
    Job,
    Source,
    SourceSection,
    Topic,
    TopicSourceSection,
    TopicTag,
)
from disp.modules.learning.schemas import JobOut, SourceOut
from disp.modules.learning.service import jobs as jobs_service
from disp.modules.learning.service.courses import FILES_DOMAIN, _authorize, _resolve_course

if TYPE_CHECKING:
    from disp.core.platform import Platform

logger = structlog.get_logger(__name__)

# §5.1: "source.content_type is a short label, not a MIME type", mapped onto
# M18's ACCEPT_DOCUMENTS entries. Restricting AcceptSpec to exactly the one
# MIME type implied by the caller-declared label is what lets M18's text-family
# resolution (store.py: `len(text_candidates) == 1`) pick the right label
# regardless of what the browser's multipart Content-Type header claims —
# four of these five have no magic-byte signature at all (§5.1).
_CONTENT_TYPE_MIME: dict[str, str] = {
    "markdown": "text/markdown",
    "html": "text/html",
    "plain_text": "text/plain",
    "srt": "application/x-subrip",
    "pdf": "application/pdf",
}

_ATX_RE = re.compile(r"^(#{1,3})\s+(\S.*?)\s*$")
_BLANK_LINE_RE = re.compile(r"\n\s*\n+")
# §8.1: "coalesced to roughly the target section size" — a plain char-count
# threshold, since no tokenizer is available at this deterministic phase.
_PLAIN_TEXT_TARGET_CHARS = 1500


@dataclass(frozen=True)
class SectionDraft:
    heading_path: str
    order_index: int
    start_ref: str | None
    end_ref: str | None
    content_text: str


@dataclass(frozen=True)
class Caption:
    """One SRT cue. Structural parsing only — no headings exist for a
    transcript, so turning captions into sections is §8.2's LLM call
    (Phase 3), not this pass. There is deliberately no DB table for this:
    captions are ephemeral, recomputed from `source.raw_text` each index run.
    """

    index: int
    start_ts: str
    end_ts: str
    text: str


def parse_source(content_type: str, raw_text: str, source_title: str) -> list[SectionDraft]:
    """§8.1's dispatch table. `srt` returns `[]` here — sectioning a
    transcript needs the LLM call in §8.2, not this deterministic pass.
    """
    if content_type == "markdown":
        return _parse_markdown(raw_text, source_title)
    if content_type == "html":
        return _parse_html(raw_text, source_title)
    if content_type in ("plain_text", "pdf"):
        return _parse_plain_text(raw_text, source_title)
    if content_type == "srt":
        return []
    raise ValueError(f"unknown content_type {content_type!r}")


def _parse_markdown(raw_text: str, source_title: str) -> list[SectionDraft]:
    """Walks H1-H3 ATX headings, skipping fenced code blocks so a `#` inside
    a shell snippet never opens a section. A heading becomes a section only
    if it owns content directly (the practical definition of "leaf" for
    prose: a heading with only child headings and no content of its own is a
    pure container and contributes no section, just a breadcrumb entry).
    Offsets are raw character offsets so `raw_text[start:end]` reproduces
    `content_text` — the property Phase 2's own verification step checks.
    """
    stack: list[tuple[int, str]] = []
    drafts: list[SectionDraft] = []
    order_index = 0
    in_fence = False
    fence_marker = ""
    pending_path = source_title
    pending_start = 0
    offset = 0

    def flush(end_offset: int) -> None:
        nonlocal order_index
        content = raw_text[pending_start:end_offset].strip()
        if content:
            drafts.append(
                SectionDraft(
                    heading_path=pending_path,
                    order_index=order_index,
                    start_ref=str(pending_start),
                    end_ref=str(end_offset),
                    content_text=content,
                )
            )
            order_index += 1

    for line in raw_text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif marker == fence_marker:
                in_fence = False
            offset += len(line)
            continue

        heading_match = None if in_fence else _ATX_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2)
            flush(offset)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            pending_path = " > ".join(t for _, t in stack)
            offset += len(line)
            pending_start = offset
            continue

        offset += len(line)

    flush(len(raw_text))
    return drafts


class _HeadingWalker(HTMLParser):
    """Tracks H1-H3 tags for `_parse_html`. `content_text` is the raw slice
    between headings (markup included) rather than tag-stripped text, for
    the same "offsets slice back to the original text" reason `_parse_markdown`
    keeps raw offsets — only a heading's own *title* is worth cleaning
    (it's a breadcrumb label, never sliced back).
    """

    def __init__(self, raw_text: str, source_title: str) -> None:
        super().__init__(convert_charrefs=True)
        self._raw_text = raw_text
        self._line_starts = self._compute_line_starts(raw_text)
        self._stack: list[tuple[int, str]] = []
        self.drafts: list[SectionDraft] = []
        self._order_index = 0
        self._pending_path = source_title
        self._pending_start = 0
        self._heading_level: int | None = None
        self._heading_parts: list[str] = []
        self._heading_start_offset = 0
        # Text seen (via handle_data) since the last flush point, tracked
        # separately from the raw offset slice: markup-only regions (e.g. a
        # bare "<html><body>" before the first heading) must not count as
        # a section's content just because the raw slice is non-whitespace.
        self._body_text_parts: list[str] = []

    @staticmethod
    def _compute_line_starts(text: str) -> list[int]:
        starts = [0]
        for line in text.splitlines(keepends=True):
            starts.append(starts[-1] + len(line))
        return starts

    def _offset(self) -> int:
        line, col = self.getpos()
        return self._line_starts[line - 1] + col

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("h1", "h2", "h3"):
            self._heading_level = int(tag[1])
            self._heading_parts = []
            self._heading_start_offset = self._offset()

    def handle_data(self, data: str) -> None:
        if self._heading_level is not None:
            self._heading_parts.append(data)
        else:
            self._body_text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag not in ("h1", "h2", "h3") or self._heading_level is None:
            return
        level = self._heading_level
        title = "".join(self._heading_parts).strip()
        self._heading_level = None
        end_offset = min(self._offset() + len(f"</{tag}>"), len(self._raw_text))

        self._flush(self._heading_start_offset)
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        self._stack.append((level, title))
        self._pending_path = " > ".join(t for _, t in self._stack)
        self._pending_start = end_offset
        self._body_text_parts = []

    def _flush(self, end_offset: int) -> None:
        if not "".join(self._body_text_parts).strip():
            return
        content = self._raw_text[self._pending_start : end_offset].strip()
        if content:
            self.drafts.append(
                SectionDraft(
                    heading_path=self._pending_path,
                    order_index=self._order_index,
                    start_ref=str(self._pending_start),
                    end_ref=str(end_offset),
                    content_text=content,
                )
            )
            self._order_index += 1

    def close_out(self) -> None:
        self._flush(len(self._raw_text))


def _parse_html(raw_text: str, source_title: str) -> list[SectionDraft]:
    walker = _HeadingWalker(raw_text, source_title)
    walker.feed(raw_text)
    walker.close_out()
    return walker.drafts


def _split_raw_blocks(raw_text: str) -> list[tuple[int, int]]:
    """Blank-line-delimited (start, end) spans, offsets into `raw_text`."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in _BLANK_LINE_RE.finditer(raw_text):
        spans.append((pos, m.start()))
        pos = m.end()
    spans.append((pos, len(raw_text)))
    return [(start, end) for start, end in spans if raw_text[start:end].strip()]


def _parse_plain_text(raw_text: str, source_title: str) -> list[SectionDraft]:
    blocks = _split_raw_blocks(raw_text)
    drafts: list[SectionDraft] = []
    order_index = 0
    cur_start: int | None = None
    cur_end: int | None = None
    cur_len = 0

    def flush(start: int, end: int) -> None:
        nonlocal order_index
        drafts.append(
            SectionDraft(
                heading_path=f"{source_title} #{order_index + 1}",
                order_index=order_index,
                start_ref=str(start),
                end_ref=str(end),
                content_text=raw_text[start:end].strip(),
            )
        )
        order_index += 1

    for start, end in blocks:
        if cur_start is None:
            cur_start, cur_end, cur_len = start, end, end - start
        elif cur_len < _PLAIN_TEXT_TARGET_CHARS:
            cur_end = end
            cur_len += end - start
        else:
            flush(cur_start, cur_end)  # type: ignore[arg-type]
            cur_start, cur_end, cur_len = start, end, end - start

    if cur_start is not None:
        flush(cur_start, cur_end)  # type: ignore[arg-type]

    return drafts


def _extract_pdf_text(raw_bytes: bytes) -> str:
    """Flat text extraction, no layout recovery (§27: PDF structure recovery
    is explicitly out of scope). Multi-column PDFs can interleave text out
    of reading order — acceptable for v1, revisit with a fixture if it proves
    unusable rather than merely degraded.
    """
    reader = PdfReader(io.BytesIO(raw_bytes))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _format_srt_timestamp(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def parse_srt_captions(raw_text: str) -> list[Caption]:
    """Structural SRT parsing (timestamps, cue text) — separate from §8.2's
    *semantic* sectioning. Malformed input yields no captions rather than
    raising; an ingest caller can then fall back to treating it as empty.
    """
    try:
        subs = list(srt_lib.parse(raw_text))
    except (srt_lib.SRTParseError, ValueError):
        return []
    return [
        Caption(
            index=sub.index,
            start_ts=_format_srt_timestamp(sub.start),
            end_ts=_format_srt_timestamp(sub.end),
            text=sub.content.replace("\n", " ").strip(),
        )
        for sub in subs
    ]


def _rough_token_count(text: str) -> int:
    """A display-only estimate, never a budget-enforcement figure — M19 §5
    forbids client-side token estimators for that. Real counting (Phase 3)
    goes through `platform.llm.count_tokens()`, which this deliberately does
    not call: Phase 2 must work with no LLM configured (§8.1)."""
    return max(1, len(text) // 4)


def _source_not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="modules.learning.source_not_found",
        title="Source not found",
        detail="The source does not exist or is not visible to you.",
    )


def _to_source_out(source: Source) -> SourceOut:
    return SourceOut(
        id=source.id,
        course_id=source.course_id,
        title=source.title,
        content_type=source.content_type,
        token_count=source.token_count,
        created_at=source.created_at,
    )


async def list_sources(
    session: AsyncSession, user: CurrentUser, course_id: UUID
) -> list[SourceOut]:
    await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "read")
    stmt = select(Source).where(Source.course_id == course_id).order_by(Source.created_at)
    rows = (await session.execute(stmt)).scalars()
    return [_to_source_out(row) for row in rows]


async def create_source(
    session: AsyncSession,
    user: CurrentUser,
    course_id: UUID,
    *,
    title: str,
    content_type: str,
    files: FileStore,
    file: UploadFile | None = None,
    raw_text: str | None = None,
) -> SourceOut:
    await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "update")

    if content_type not in _CONTENT_TYPE_MIME:
        raise AppError(
            status_code=415,
            code="modules.learning.unsupported_content_type",
            title="Unsupported content type",
            detail=f"content_type must be one of {sorted(_CONTENT_TYPE_MIME)}.",
        )

    settings = get_learning_settings()
    existing_count = await session.scalar(
        select(func.count()).select_from(Source).where(Source.course_id == course_id)
    )
    if (existing_count or 0) >= settings.max_sources_per_course:
        raise AppError(
            status_code=409,
            code="modules.learning.source_limit",
            title="Source limit reached",
            detail=f"A course may have at most {settings.max_sources_per_course} sources.",
        )

    file_id: UUID | None = None
    if file is not None:
        accept = AcceptSpec(
            content_types=frozenset({_CONTENT_TYPE_MIME[content_type]}),
            max_bytes=settings.max_source_bytes,
        )
        # Read once, capped one byte past the limit so put() still sees (and
        # 413s) an over-sized upload; extract from these same bytes rather
        # than downloading them back from the bucket (M18-files.md §7).
        raw_bytes = await file.read(settings.max_source_bytes + 1)
        stored = await files.put(
            session,
            owner=user,
            domain=FILES_DOMAIN,
            purpose="source",
            source=raw_bytes,
            name=file.filename,
            accept=accept,
        )
        file_id = stored.id
        extracted = (
            _extract_pdf_text(raw_bytes) if content_type == "pdf" else raw_bytes.decode("utf-8")
        )
    else:
        # Exactly one of file/raw_text is meaningful; a file (when given)
        # always wins over a simultaneously-supplied raw_text rather than
        # 400ing on the combination — simpler than inventing a new error
        # code for a caller mistake with an obvious, harmless resolution.
        extracted = raw_text or ""

    extracted = extracted.strip()
    if not extracted:
        raise AppError(
            status_code=400,
            code="modules.learning.empty_source",
            title="Empty source",
            detail="The source has no extractable text.",
        )

    source = Source(
        course_id=course_id,
        title=title,
        content_type=content_type,
        file_id=file_id,
        raw_text=extracted,
        token_count=_rough_token_count(extracted),
    )
    session.add(source)
    await session.flush()

    for draft in parse_source(content_type, extracted, title):
        session.add(
            SourceSection(
                source_id=source.id,
                heading_path=draft.heading_path,
                order_index=draft.order_index,
                start_ref=draft.start_ref,
                end_ref=draft.end_ref,
                content_text=draft.content_text,
                token_count=_rough_token_count(draft.content_text),
            )
        )

    return _to_source_out(source)


async def delete_source(
    session: AsyncSession, user: CurrentUser, source_id: UUID, *, files: FileStore
) -> None:
    source = await session.get(Source, source_id)
    if source is None:
        raise _source_not_found_error()
    await _resolve_course(session, source.course_id)
    await _authorize(session, user, source.course_id, "update")

    if source.file_id is not None:
        # I2 (M18 §2): delete() only marks the row; the bytes leave the
        # bucket after this transaction commits — safe to call here.
        await files.delete(session, source.file_id, domain=FILES_DOMAIN)
    await session.delete(source)


# --- §8.2-§8.5, §16: indexing job ------------------------------------------

_SEGMENT_TRANSCRIPT_CALL = LLMCall(
    name="learning.segment_transcript",
    schema=llm_schemas.TranscriptSegments,
    system=prompts.SEGMENT_TRANSCRIPT_SYSTEM,
    max_output_tokens=2000,
)
_ALIGN_TOPICS_CALL = LLMCall(
    name="learning.align_topics",
    schema=llm_schemas.TopicAlignment,
    system=prompts.ALIGN_TOPICS_SYSTEM,
    max_output_tokens=8000,
)
_GENERATE_TAGS_CALL = LLMCall(
    name="learning.generate_tags",
    schema=llm_schemas.TopicTags,
    system=prompts.GENERATE_TAGS_SYSTEM,
    max_output_tokens=500,
)
_SUMMARIZE_TOPIC_CALL = LLMCall(
    name="learning.summarize_topic",
    schema=llm_schemas.TopicSummary,
    system=prompts.SUMMARIZE_TOPIC_SYSTEM,
    max_output_tokens=500,
)

# §8.2: a rough character-based budget for the map step's chunk boundaries —
# matches `_rough_token_count`'s reasoning rather than calling
# `count_tokens()` per candidate boundary.
_SRT_CHUNK_TARGET_CHARS = 4000 * 4


async def create_index_job(
    session: AsyncSession, user: CurrentUser, course_id: UUID
) -> tuple[JobOut, str]:
    """Creates the `job` row and returns its wire representation, uncommitted
    — the caller's transaction commits it, and only then defers the task
    (§16.2: deferring first races the worker against the row's own
    transaction)."""
    await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "update")
    job = await jobs_service.create_job(
        session, course_id=course_id, user_id=user.id, kind="index_course"
    )
    return jobs_service.to_job_out(job), "learning.index_course"


def _chunk_captions(captions: list[Caption]) -> list[list[Caption]]:
    """Splits only on caption boundaries, carrying the last caption of one
    chunk over as the first of the next, so a concept discussed across a
    chunk boundary is not sliced in half (§8.2)."""
    if not captions:
        return []
    chunks: list[list[Caption]] = []
    current: list[Caption] = []
    current_chars = 0
    for caption in captions:
        current.append(caption)
        current_chars += len(caption.text)
        if current_chars >= _SRT_CHUNK_TARGET_CHARS:
            chunks.append(current)
            current = [caption]
            current_chars = len(caption.text)
    if current and (not chunks or len(current) > 1):
        chunks.append(current)
    return chunks


def _render_captions(captions: list[Caption]) -> str:
    return "\n".join(f"[{c.start_ts} - {c.end_ts}] {c.text}" for c in captions)


def _captions_text_between(captions: list[Caption], start_ts: str, end_ts: str) -> str:
    return " ".join(c.text for c in captions if start_ts <= c.start_ts <= end_ts)


async def _segment_source(
    platform: "Platform", raw_text: str, *, user_id: UUID
) -> list[llm_schemas.TranscriptSegment]:
    captions = parse_srt_captions(raw_text)
    if not captions:
        return []
    settings = get_settings()
    segments: list[llm_schemas.TranscriptSegment] = []
    for chunk in _chunk_captions(captions):
        out = cast(
            llm_schemas.TranscriptSegments,
            await platform.llm.generate(
                _SEGMENT_TRANSCRIPT_CALL,
                _render_captions(chunk),
                user_id=user_id,
                model=settings.llm_fast_model,
            ),
        )
        segments.extend(out.segments)
    return segments


async def _write_srt_sections(
    session: AsyncSession,
    source_id: UUID,
    raw_text: str,
    segments: list[llm_schemas.TranscriptSegment],
) -> None:
    captions = parse_srt_captions(raw_text)
    await session.execute(delete(SourceSection).where(SourceSection.source_id == source_id))
    for i, seg in enumerate(segments):
        content = _captions_text_between(captions, seg.start_ts, seg.end_ts)
        session.add(
            SourceSection(
                source_id=source_id,
                heading_path=seg.label,
                order_index=i,
                start_ref=seg.start_ts,
                end_ref=seg.end_ts,
                content_text=content,
                token_count=_rough_token_count(content),
            )
        )


async def _load_headings(session: AsyncSession, course_id: UUID) -> list[dict[str, str]]:
    stmt = (
        select(Source.id, Source.title, SourceSection.id, SourceSection.heading_path)
        .join(SourceSection, SourceSection.source_id == Source.id)
        .where(Source.course_id == course_id)
        .order_by(Source.created_at, SourceSection.order_index)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "source_id": str(source_id),
            "source_title": source_title,
            "section_id": str(section_id),
            "heading_path": heading_path,
        }
        for source_id, source_title, section_id, heading_path in rows
    ]


def _render_headings(headings: list[dict[str, str]]) -> str:
    return "\n".join(
        f"- source_id={h['source_id']} section_id={h['section_id']} "
        f"source_title={h['source_title']!r} heading_path={h['heading_path']!r}"
        for h in headings
    )


async def _align_topics(
    platform: "Platform", headings: list[dict[str, str]], *, user_id: UUID
) -> llm_schemas.TopicAlignment:
    result = await platform.llm.generate(
        _ALIGN_TOPICS_CALL, _render_headings(headings), user_id=user_id
    )
    return cast(llm_schemas.TopicAlignment, result)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


async def _embedding_fallback(
    session: AsyncSession,
    platform: "Platform",
    alignment: llm_schemas.TopicAlignment,
    *,
    user_id: UUID,
) -> dict[UUID, str]:
    """§8.3: for each unmatched section, embed it and every candidate
    topic's description, and assign to the highest-cosine topic above
    `alignment_similarity_threshold`. Below threshold, the section is left
    genuinely unmatched — never forced onto the nearest topic anyway, since
    a wrongly-placed section silently corrupts that topic's later quiz
    questions, while an unmatched one is a visible review item (§8.3).
    """
    if not alignment.unmatched_section_ids or not alignment.topics:
        return {}
    settings = get_learning_settings()
    sections = list(
        (
            await session.execute(
                select(SourceSection).where(SourceSection.id.in_(alignment.unmatched_section_ids))
            )
        ).scalars()
    )
    if not sections:
        return {}

    texts = [s.content_text for s in sections] + [t.description for t in alignment.topics]
    vectors = await platform.llm.embed(texts, user_id=user_id)
    section_vectors = vectors[: len(sections)]
    topic_vectors = vectors[len(sections) :]

    resolved: dict[UUID, str] = {}
    for section, section_vec in zip(sections, section_vectors, strict=True):
        best_name: str | None = None
        best_score = -1.0
        for topic_out, topic_vec in zip(alignment.topics, topic_vectors, strict=True):
            score = _cosine_similarity(section_vec, topic_vec)
            if score > best_score:
                best_score, best_name = score, topic_out.name
        if best_name is not None and best_score >= settings.alignment_similarity_threshold:
            resolved[section.id] = best_name
    return resolved


async def _reconcile_topics(
    session: AsyncSession,
    course_id: UUID,
    alignment: llm_schemas.TopicAlignment,
    fallback_resolved: dict[UUID, str],
) -> dict[str, UUID]:
    """§8.5: match on `canonical_name` (`uq_topic_course_name` is exactly
    this key). A matched topic keeps its id, and so its `topic_tag` and
    `topic_tag_score` history; a topic no longer produced this run is
    deleted, cascading its tags and scores, and unanchoring any note that
    pointed at it (`ON DELETE SET NULL`). Returns {canonical_name: topic_id}
    for topics newly created this run — the tagging/summarizing phase
    iterates only this set (§8.4): a matched topic must never re-enter tag
    generation, or a model rephrasing a tag slightly forks a second
    `topic_tag` row with no score history.
    """
    existing = {
        t.canonical_name: t
        for t in (
            await session.execute(select(Topic).where(Topic.course_id == course_id))
        ).scalars()
    }

    member_map: dict[str, list[UUID]] = {
        t.name: list(t.member_section_ids) for t in alignment.topics
    }
    for section_id, topic_name in fallback_resolved.items():
        member_map.setdefault(topic_name, []).append(section_id)

    new_topic_ids: dict[str, UUID] = {}
    seen_names: set[str] = set()
    for topic_out in alignment.topics:
        seen_names.add(topic_out.name)
        if topic_out.name in existing:
            row = existing[topic_out.name]
            row.description = topic_out.description
        else:
            row = Topic(
                course_id=course_id,
                canonical_name=topic_out.name,
                description=topic_out.description,
            )
            session.add(row)
            await session.flush()
            new_topic_ids[topic_out.name] = row.id

        await session.execute(
            delete(TopicSourceSection).where(TopicSourceSection.topic_id == row.id)
        )
        session.add_all(
            TopicSourceSection(topic_id=row.id, source_section_id=section_id)
            for section_id in member_map[topic_out.name]
        )

    for stale_name in existing.keys() - seen_names:
        await session.delete(existing[stale_name])

    return new_topic_ids


async def _load_topic_text(session: AsyncSession, topic_id: UUID) -> str:
    stmt = (
        select(SourceSection.content_text)
        .join(TopicSourceSection, TopicSourceSection.source_section_id == SourceSection.id)
        .where(TopicSourceSection.topic_id == topic_id)
        .order_by(SourceSection.order_index)
    )
    return "\n\n".join((await session.execute(stmt)).scalars())


async def _tag_and_summarize_topic(
    platform: "Platform", session: AsyncSession, topic_id: UUID, *, user_id: UUID
) -> None:
    text = await _load_topic_text(session, topic_id)
    settings = get_settings()
    tags_out = cast(
        llm_schemas.TopicTags,
        await platform.llm.generate(
            _GENERATE_TAGS_CALL, text, user_id=user_id, model=settings.llm_fast_model
        ),
    )
    summary_out = cast(
        llm_schemas.TopicSummary,
        await platform.llm.generate(
            _SUMMARIZE_TOPIC_CALL, text, user_id=user_id, model=settings.llm_fast_model
        ),
    )

    topic = await session.get(Topic, topic_id)
    if topic is None:
        raise RuntimeError(f"topic {topic_id} vanished mid-index (reconciled this run)")
    topic.aggregated_summary = summary_out.summary
    session.add_all(TopicTag(topic_id=topic_id, name=name) for name in tags_out.names)


def _map_index_error_code(exc: Exception) -> str:
    if isinstance(exc, LLMNotConfigured | LLMUnavailable):
        return "modules.learning.llm_unavailable"
    if isinstance(exc, LLMRefused):
        return "modules.learning.llm_refused"
    return "modules.learning.index_failed"


async def run_index_job(platform: "Platform", job_id: UUID) -> None:
    """The `learning.index_course` task body (§16.2). Owns every
    `session_scope()` call — one per phase boundary, so progress is visible
    before the whole job commits. LLM calls always run outside an open
    transaction; only the reconciling phase is a single transaction, because
    a half-renamed topic set is a state every later read (quiz gen, path
    gen, chat) would observe inconsistently.
    """
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            raise RuntimeError(f"job {job_id} not found at run_index_job start")
        course_id, user_id = job.course_id, job.user_id
        await jobs_service.mark_running(session, job_id)
        course = await session.get(Course, course_id)
        if course is None:
            raise RuntimeError(f"course {course_id} not found at run_index_job start")
        previous_status = course.status
        course.status = "indexing"

    try:
        async with session_scope() as session:
            srt_sources = list(
                (
                    await session.execute(
                        select(Source).where(
                            Source.course_id == course_id, Source.content_type == "srt"
                        )
                    )
                ).scalars()
            )
            await jobs_service.update_progress(
                session, job_id, phase="segmenting", current=0, total=len(srt_sources)
            )

        for i, src in enumerate(srt_sources):
            segments = await _segment_source(platform, src.raw_text, user_id=user_id)
            async with session_scope() as session:
                await _write_srt_sections(session, src.id, src.raw_text, segments)
                await jobs_service.update_progress(
                    session,
                    job_id,
                    phase="segmenting",
                    current=i + 1,
                    total=len(srt_sources),
                )

        async with session_scope() as session:
            await jobs_service.update_progress(
                session, job_id, phase="aligning", current=0, total=1
            )
            headings = await _load_headings(session, course_id)
        alignment = await _align_topics(platform, headings, user_id=user_id)

        async with session_scope() as session:
            await jobs_service.update_progress(
                session, job_id, phase="embedding_fallback", current=0, total=1
            )
            fallback_resolved = await _embedding_fallback(
                session, platform, alignment, user_id=user_id
            )

        async with session_scope() as session:
            new_topic_ids = await _reconcile_topics(
                session, course_id, alignment, fallback_resolved
            )
            await jobs_service.update_progress(
                session, job_id, phase="tagging", current=0, total=len(new_topic_ids)
            )

        for i, topic_id in enumerate(new_topic_ids.values()):
            async with session_scope() as session:
                await _tag_and_summarize_topic(platform, session, topic_id, user_id=user_id)
                await jobs_service.update_progress(
                    session,
                    job_id,
                    phase="tagging",
                    current=i + 1,
                    total=len(new_topic_ids),
                )

        async with session_scope() as session:
            course = await session.get(Course, course_id)
            if course is None:
                raise RuntimeError(f"course {course_id} vanished mid-index")
            course.status = "active"
            await jobs_service.mark_succeeded(session, job_id)
            topic_count = await session.scalar(
                select(func.count()).select_from(Topic).where(Topic.course_id == course_id)
            )
            publish_after_commit(
                session,
                CourseIndexed(
                    course_id=course_id,
                    user_id=user_id,
                    topic_count=topic_count or 0,
                    unmatched_count=len(alignment.unmatched_section_ids) - len(fallback_resolved),
                ),
            )

        await platform.notifier.send(
            user_id,
            "learning.index_ready",
            "Course indexed",
            "Your course finished indexing and is ready to study.",
            url=f"/learning/{course_id}",
        )
    except Exception as exc:
        logger.warning("learning_index_course_failed", course_id=str(course_id), error=str(exc))
        async with session_scope() as session:
            await jobs_service.mark_failed(session, job_id, error_code=_map_index_error_code(exc))
            course = await session.get(Course, course_id)
            if course is not None:
                course.status = previous_status
        raise
