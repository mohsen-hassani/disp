"""M20 §8.1 (Phase 2): deterministic ingestion parsing plus source CRUD.

The parser tests take no DB and no LLM — that is the property `M20` §4
exists to verify ("this step is deterministic and MUST be independently
testable with no LLM configured"). The `parse_source` dispatch is tested
against every `content_type` `learning.source.content_type` accepts.
"""

from io import BytesIO
from uuid import uuid4

import httpx
import pytest
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.config import get_settings
from disp.core.errors import AppError
from disp.core.files import FileStore
from disp.modules.learning.models import Course, Source, SourceSection
from disp.modules.learning.schemas import CourseCreate
from disp.modules.learning.service.courses import create_course
from disp.modules.learning.service.ingest import (
    create_source,
    delete_source,
    list_sources,
    parse_source,
    parse_srt_captions,
)
from tests.factories import current_user_for, make_user

MARKDOWN_SOURCE = """\
Some intro text before any heading.

# Chapter 1

Chapter 1 intro paragraph.

## Setup

Install the tool first.

```python
# a comment that must not be mistaken for a heading
```

More setup text after the fence.

## Teardown

Clean up after yourself.

# Chapter 2

Only chapter-level content, no subheadings.
"""

HTML_SOURCE = (
    "<html><body>"
    "<h1>Chapter 1</h1>"
    "<p>Chapter 1 intro.</p>"
    "<h2>Setup</h2>"
    "<p>Install the tool.</p>"
    "<h2>Teardown</h2>"
    "<p>Clean up.</p>"
    "</body></html>"
)

PLAIN_TEXT_SOURCE = "First block.\n\nSecond block.\n\nThird block.\n"

# Two ~900-char blocks (over the 1500-char coalescing target together) plus a
# third short one — exercises both coalescing (short blocks merge) and
# size-triggered splitting (the accumulator flushes once it crosses target).
_BIG_BLOCK_A = "Alpha sentence. " * 60
_BIG_BLOCK_B = "Beta sentence. " * 60
PLAIN_TEXT_LARGE_SOURCE = f"{_BIG_BLOCK_A}\n\n{_BIG_BLOCK_B}\n\nTail block.\n"

SRT_SOURCE = """\
1
00:00:01,000 --> 00:00:04,000
Hello there.

2
00:00:04,500 --> 00:00:08,000
This is the second caption,
split across two lines.
"""


def _files(session_maker: async_sessionmaker[AsyncSession] | None = None) -> FileStore:
    # A private key prefix in the shared MinIO bucket; the per-test
    # session_maker (when given) lets post-commit purges see this test's rows.
    settings = get_settings().model_copy(update={"files_s3_prefix": f"t-{uuid4().hex}/"})
    return FileStore.from_settings(settings, session_maker=session_maker)


async def _bucket_keys(files: FileStore) -> set[str]:
    return {key async for key, _ in files.backend.iter_objects(files.prefix)}


def _upload(data: bytes, filename: str) -> UploadFile:
    return UploadFile(file=BytesIO(data), filename=filename)


async def _owner_course(session: AsyncSession, email: str) -> tuple[object, Course]:
    user = await make_user(session, email=email)
    cu = current_user_for(user)
    out = await create_course(session, cu, CourseCreate(title="Design Patterns"))
    row = (await session.execute(select(Course).where(Course.id == out.id))).scalar_one()
    return cu, row


# --- Pure parser tests: no DB, no LLM -------------------------------------


def test_parse_markdown_headings_are_correct_breadcrumbs() -> None:
    drafts = parse_source("markdown", MARKDOWN_SOURCE, "Book")
    paths = [d.heading_path for d in drafts]
    assert paths == [
        "Book",  # preamble before the first heading
        "Chapter 1",
        "Chapter 1 > Setup",
        "Chapter 1 > Teardown",
        "Chapter 2",
    ]


def test_parse_markdown_skips_headings_inside_fenced_code_blocks() -> None:
    drafts = parse_source("markdown", MARKDOWN_SOURCE, "Book")
    # The `# a comment...` line inside the fence must never open a section —
    # if it did, "Setup" would be followed by a spurious heading before
    # "More setup text after the fence." lands back under "Setup".
    setup = next(d for d in drafts if d.heading_path == "Chapter 1 > Setup")
    assert "More setup text after the fence." in setup.content_text
    assert "a comment that must not be mistaken" in setup.content_text


def test_parse_markdown_offsets_slice_back_to_the_original_text() -> None:
    drafts = parse_source("markdown", MARKDOWN_SOURCE, "Book")
    for draft in drafts:
        assert draft.start_ref is not None
        assert draft.end_ref is not None
        start, end = int(draft.start_ref), int(draft.end_ref)
        assert MARKDOWN_SOURCE[start:end].strip() == draft.content_text


def test_parse_html_headings_and_offsets() -> None:
    drafts = parse_source("html", HTML_SOURCE, "Book")
    paths = [d.heading_path for d in drafts]
    assert paths == ["Chapter 1", "Chapter 1 > Setup", "Chapter 1 > Teardown"]
    for draft in drafts:
        start, end = int(draft.start_ref), int(draft.end_ref)
        assert HTML_SOURCE[start:end].strip() == draft.content_text


def test_parse_plain_text_coalesces_short_blocks_into_one_section() -> None:
    # Well under the 1500-char coalescing target in total, so all three
    # blank-line-delimited blocks merge into a single section (§8.1:
    # "coalesced to roughly the target section size").
    drafts = parse_source("plain_text", PLAIN_TEXT_SOURCE, "Notes")
    assert len(drafts) == 1
    assert drafts[0].heading_path == "Notes #1"
    for block in ("First block.", "Second block.", "Third block."):
        assert block in drafts[0].content_text


def test_parse_plain_text_splits_once_the_accumulator_crosses_target_size() -> None:
    drafts = parse_source("plain_text", PLAIN_TEXT_LARGE_SOURCE, "Notes")
    assert len(drafts) == 2
    # The first two blocks (~1860 chars combined) coalesce past the 1500-char
    # target and flush together; the short tail block starts a fresh section.
    assert "Alpha sentence." in drafts[0].content_text
    assert "Beta sentence." in drafts[0].content_text
    assert drafts[1].content_text == "Tail block."
    for draft in drafts:
        start, end = int(draft.start_ref), int(draft.end_ref)
        assert PLAIN_TEXT_LARGE_SOURCE[start:end].strip() == draft.content_text


def test_parse_srt_returns_no_sections_in_phase_two() -> None:
    # §8.1: sectioning a transcript needs the LLM call in §8.2 (Phase 3).
    assert parse_source("srt", SRT_SOURCE, "Lecture") == []


def test_parse_srt_captions_structural_parse() -> None:
    captions = parse_srt_captions(SRT_SOURCE)
    assert len(captions) == 2
    assert captions[0].start_ts == "00:00:01"
    assert captions[0].end_ts == "00:00:04"
    assert captions[0].text == "Hello there."
    # Multi-line cue text is joined onto one line.
    assert captions[1].text == "This is the second caption, split across two lines."


def test_parse_srt_captions_malformed_input_returns_empty() -> None:
    assert parse_srt_captions("not an srt file at all") == []


# --- Service-level tests: real DB, real (tmp_path) file store ------------


async def test_create_source_from_pasted_markdown_creates_sections(
    db_session: AsyncSession,
) -> None:
    cu, course = await _owner_course(db_session, "learning-ingest-paste@example.com")

    out = await create_source(
        db_session,
        cu,
        course.id,
        title="Pasted notes",
        content_type="markdown",
        files=_files(),
        raw_text=MARKDOWN_SOURCE,
    )
    await db_session.flush()

    row = (await db_session.execute(select(Source).where(Source.id == out.id))).scalar_one()
    assert row.file_id is None
    assert row.raw_text == MARKDOWN_SOURCE.strip()

    sections = (
        await db_session.execute(
            select(SourceSection)
            .where(SourceSection.source_id == row.id)
            .order_by(SourceSection.order_index)
        )
    ).scalars()
    headings = [s.heading_path for s in sections]
    assert headings == [
        "Pasted notes",
        "Chapter 1",
        "Chapter 1 > Setup",
        "Chapter 1 > Teardown",
        "Chapter 2",
    ]


async def test_create_source_from_uploaded_file_round_trips_through_file_store(
    db_session: AsyncSession,
) -> None:
    cu, course = await _owner_course(db_session, "learning-ingest-upload@example.com")
    files = _files()

    out = await create_source(
        db_session,
        cu,
        course.id,
        title="Uploaded notes",
        content_type="markdown",
        files=files,
        file=_upload(MARKDOWN_SOURCE.encode("utf-8"), "notes.md"),
    )
    await db_session.flush()

    row = (await db_session.execute(select(Source).where(Source.id == out.id))).scalar_one()
    assert row.file_id is not None
    assert row.raw_text == MARKDOWN_SOURCE.strip()

    stored = await files.get(db_session, row.file_id, domain="learning")
    assert stored is not None
    assert stored.content_type == "text/markdown"
    assert stored.name == "notes.md"
    link = await files.link(db_session, row.file_id, domain="learning")
    async with httpx.AsyncClient() as http:
        response = await http.get(link.url)
    assert response.content == MARKDOWN_SOURCE.encode("utf-8")
    # Text family: always a download, never rendered (M18 I6).
    assert response.headers["content-disposition"].startswith("attachment;")


async def test_oversized_upload_is_rejected_without_reaching_the_bucket(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from disp.modules.learning.config import get_learning_settings

    monkeypatch.setenv("DISP_LEARNING_MAX_SOURCE_BYTES", "64")
    get_learning_settings.cache_clear()
    try:
        cu, course = await _owner_course(db_session, "learning-ingest-big@example.com")
        files = _files()
        with pytest.raises(AppError) as exc_info:
            await create_source(
                db_session,
                cu,
                course.id,
                title="Too big",
                content_type="plain_text",
                files=files,
                file=_upload(b"x" * 1000, "big.txt"),
            )
        assert exc_info.value.code == "core.files.too_large"
        assert await _bucket_keys(files) == set()
    finally:
        get_learning_settings.cache_clear()


async def test_create_source_rejects_unsupported_content_type(db_session: AsyncSession) -> None:
    cu, course = await _owner_course(db_session, "learning-ingest-badtype@example.com")

    with pytest.raises(AppError) as exc_info:
        await create_source(
            db_session,
            cu,
            course.id,
            title="Bad",
            content_type="epub",
            files=_files(),
            raw_text="whatever",
        )
    assert exc_info.value.status_code == 415
    assert exc_info.value.code == "modules.learning.unsupported_content_type"


async def test_create_source_rejects_empty_extracted_text(db_session: AsyncSession) -> None:
    cu, course = await _owner_course(db_session, "learning-ingest-empty@example.com")

    with pytest.raises(AppError) as exc_info:
        await create_source(
            db_session,
            cu,
            course.id,
            title="Empty",
            content_type="plain_text",
            files=_files(),
            raw_text="   \n\n  ",
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "modules.learning.empty_source"


async def test_create_source_enforces_source_limit(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from disp.modules.learning.config import get_learning_settings

    monkeypatch.setenv("DISP_LEARNING_MAX_SOURCES_PER_COURSE", "1")
    get_learning_settings.cache_clear()
    try:
        cu, course = await _owner_course(db_session, "learning-ingest-limit@example.com")
        files = _files()
        await create_source(
            db_session,
            cu,
            course.id,
            title="First",
            content_type="plain_text",
            files=files,
            raw_text="content one",
        )
        await db_session.flush()

        with pytest.raises(AppError) as exc_info:
            await create_source(
                db_session,
                cu,
                course.id,
                title="Second",
                content_type="plain_text",
                files=files,
                raw_text="content two",
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "modules.learning.source_limit"
    finally:
        get_learning_settings.cache_clear()


async def test_list_sources_on_unreadable_course_returns_404(db_session: AsyncSession) -> None:
    _owner_cu, course = await _owner_course(db_session, "learning-ingest-owner2@example.com")
    stranger = await make_user(db_session, email="learning-ingest-stranger@example.com")

    with pytest.raises(AppError) as exc_info:
        await list_sources(db_session, current_user_for(stranger), course.id)
    assert exc_info.value.status_code == 404


async def test_delete_source_removes_row_and_deletes_its_file(
    db_session: AsyncSession, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    cu, course = await _owner_course(db_session, "learning-ingest-delete@example.com")
    files = _files(session_maker)

    out = await create_source(
        db_session,
        cu,
        course.id,
        title="To delete",
        content_type="plain_text",
        files=files,
        file=_upload(b"some content to delete", "notes.txt"),
    )
    await db_session.commit()
    row = (await db_session.execute(select(Source).where(Source.id == out.id))).scalar_one()
    file_id = row.file_id
    assert file_id is not None
    assert len(await _bucket_keys(files)) == 1

    await delete_source(db_session, cu, out.id, files=files)
    await db_session.commit()
    await files.wait_for_purges()

    remaining = (
        await db_session.execute(select(Source).where(Source.id == out.id))
    ).scalar_one_or_none()
    assert remaining is None
    assert await files.get(db_session, file_id, domain="learning") is None
    assert await _bucket_keys(files) == set()


async def test_delete_course_deletes_every_source_file(
    db_session: AsyncSession, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    """M18 §8.4: the course is only soft-deleted and its sources live on, so
    before v2 their uploads stayed in storage forever."""
    from disp.modules.learning.service.courses import delete_course

    cu, course = await _owner_course(db_session, "learning-ingest-course-del@example.com")
    files = _files(session_maker)
    for name in ("a.txt", "b.txt"):
        await create_source(
            db_session,
            cu,
            course.id,
            title=name,
            content_type="plain_text",
            files=files,
            file=_upload(f"content of {name}".encode(), name),
        )
    await create_source(
        db_session,
        cu,
        course.id,
        title="pasted",
        content_type="plain_text",
        files=files,
        raw_text="pasted, no file",
    )
    await db_session.commit()
    assert len(await _bucket_keys(files)) == 2

    await delete_course(db_session, cu, course.id, files=files)
    await db_session.commit()
    await files.wait_for_purges()

    assert await _bucket_keys(files) == set()
