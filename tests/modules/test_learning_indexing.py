"""M20 §8.2-§8.5, §16 (Phase 3): indexing, the job surface, and alignment.

`run_index_job` deliberately owns its own `session_scope()` calls (§16.2) —
it never takes an injected session, because a real background task never
has a request-scoped one. That means it opens genuinely separate
connections from this test's `db_session`, which is bound to a per-test
SAVEPOINT and never actually commits to the shared database (`CLAUDE.md`'s
testing section; the same reasoning `tests/cli/conftest.py`'s `cli_db`
fixture documents for CLI tests). So the end-to-end tests here use a
REAL-commit session for setup and assertions, exactly like `cli_db` — both
point at the same testcontainers Postgres, and ordinary read-committed
semantics make one side's commits visible to the other.
"""

import itertools
import os
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.config import get_settings
from disp.core.db import create_engine, create_session_maker
from disp.core.errors import AppError
from disp.core.files import FileStore
from disp.core.llm import FakeLLM, LLMRefused
from disp.modules.learning.llm_schemas import (
    AlignedTopic,
    TopicAlignment,
    TopicSummary,
    TopicTags,
)
from disp.modules.learning.models import (
    Course,
    Job,
    Note,
    Source,
    SourceSection,
    Topic,
    TopicTag,
    TopicTagScore,
)
from disp.modules.learning.schemas import CourseCreate
from disp.modules.learning.service.courses import create_course
from disp.modules.learning.service.ingest import (
    Caption,
    _chunk_captions,
    _cosine_similarity,
    create_index_job,
)
from disp.modules.learning.service.ingest import run_index_job as run_index_job_impl
from tests.factories import current_user_for, make_user

MARKDOWN_SOURCE = "# Singletons\n\nA singleton restricts a class to one instance.\n"


def _files() -> FileStore:
    # Sources here are pasted, never uploaded: the store is never called.
    return FileStore.from_settings(get_settings())


class _RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[UUID, str, str, str, str | None]] = []

    async def send(
        self,
        user_id: UUID,
        notification_type: str,
        title: str,
        body: str,
        url: str | None = None,
    ) -> None:
        self.sent.append((user_id, notification_type, title, body, url))


def _platform(llm: FakeLLM, notifier: _RecordingNotifier) -> SimpleNamespace:
    return SimpleNamespace(llm=llm, notifier=notifier)


@pytest.fixture
async def real_db() -> AsyncIterator[AsyncSession]:
    """A real-commit session pointed at the same testcontainers Postgres
    `db_session` uses — needed because `run_index_job` opens its own
    connections via bare `session_scope()` and can only see committed rows.
    """
    engine = create_engine(os.environ["DISP_DATABASE_URL"])
    maker = create_session_maker(engine)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seeded_course(
    real_db: AsyncSession, tmp_path: Path, email: str
) -> tuple[object, Course, SourceSection]:
    from disp.modules.learning.service.ingest import create_source

    user = await make_user(real_db, email=email)
    cu = current_user_for(user)
    course_out = await create_course(real_db, cu, CourseCreate(title="Design Patterns"))
    await create_source(
        real_db,
        cu,
        course_out.id,
        title="Notes",
        content_type="markdown",
        files=_files(),
        raw_text=MARKDOWN_SOURCE,
    )
    await real_db.commit()

    course = (await real_db.execute(select(Course).where(Course.id == course_out.id))).scalar_one()
    section = (
        (
            await real_db.execute(
                select(SourceSection)
                .join(Source, Source.id == SourceSection.source_id)
                .where(Source.course_id == course.id)
            )
        )
        .scalars()
        .first()
    )
    assert section is not None
    return cu, course, section


# --- Pure helpers: no DB, no LLM -------------------------------------------


def test_cosine_similarity_identical_vectors_is_one() -> None:
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_is_zero() -> None:
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector_is_zero_not_a_division_error() -> None:
    assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_chunk_captions_splits_only_on_caption_boundaries_with_overlap() -> None:
    captions = [
        Caption(index=i, start_ts=f"00:00:{i:02d}", end_ts=f"00:00:{i + 1:02d}", text="x" * 50)
        for i in range(1, 400)
    ]
    chunks = _chunk_captions(captions)
    assert len(chunks) > 1
    # Every caption boundary in a chunk is a real caption, never a fragment.
    for chunk in chunks:
        assert all(isinstance(c, Caption) for c in chunk)
    # Consecutive chunks share exactly one overlapping caption.
    for prev_chunk, next_chunk in itertools.pairwise(chunks):
        assert prev_chunk[-1].index == next_chunk[0].index


def test_chunk_captions_empty_input() -> None:
    assert _chunk_captions([]) == []


# --- create_index_job: ordinary session, no background task involved ------


async def test_create_index_job_second_call_while_active_conflicts(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session, email="learning-index-conflict@example.com")
    cu = current_user_for(user)
    course = await create_course(db_session, cu, CourseCreate(title="Design Patterns"))

    job_out, task_name = await create_index_job(db_session, cu, course.id)
    await db_session.flush()
    assert task_name == "learning.index_course"
    assert job_out.status == "queued"

    with pytest.raises(AppError) as exc_info:
        await create_index_job(db_session, cu, course.id)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "modules.learning.job_already_running"


async def test_create_index_job_on_unreadable_course_returns_404(
    db_session: AsyncSession,
) -> None:
    owner = await make_user(db_session, email="learning-index-owner@example.com")
    stranger = await make_user(db_session, email="learning-index-stranger@example.com")
    course = await create_course(db_session, current_user_for(owner), CourseCreate(title="Private"))

    with pytest.raises(AppError) as exc_info:
        await create_index_job(db_session, current_user_for(stranger), course.id)
    assert exc_info.value.status_code == 404


# --- run_index_job: real background-task semantics -------------------------


async def test_index_job_happy_path_creates_topic_tags_and_summary(
    real_db: AsyncSession, tmp_path: Path
) -> None:
    _cu, course, section = await _seeded_course(
        real_db, tmp_path, "learning-index-happy@example.com"
    )
    course_id, user_id, section_id = course.id, course.user_id, section.id

    job = Job(course_id=course_id, user_id=user_id, kind="index_course")
    real_db.add(job)
    await real_db.commit()
    job_id = job.id

    fake_llm = FakeLLM()
    fake_llm.register(
        "learning.align_topics",
        TopicAlignment(
            topics=[
                AlignedTopic(
                    name="Singleton pattern",
                    description="Restricting a class to one instance.",
                    member_section_ids=[section_id],
                )
            ],
            unmatched_section_ids=[],
        ),
    )
    fake_llm.register(
        "learning.generate_tags",
        TopicTags(
            names=[
                "explains the singleton pattern",
                "identifies its trade-offs",
                "spots misuse",
            ]
        ),
    )
    fake_llm.register(
        "learning.summarize_topic",
        TopicSummary(summary="Singletons restrict instantiation to a single shared instance."),
    )
    notifier = _RecordingNotifier()
    platform = _platform(fake_llm, notifier)

    await run_index_job_impl(platform, job_id)  # type: ignore[arg-type]

    # `run_index_job_impl` wrote through entirely separate connections, so
    # `real_db`'s identity-mapped objects (course, section, job) are stale
    # in-memory until forced to reload. `expire_all()` forces that reload on
    # the next query, but the reload itself must happen inside an awaited
    # `execute()` — touching a *specific* now-expired object's attribute
    # directly (e.g. `course.id`) outside of one raises MissingGreenlet, so
    # every query below seeks by the plain UUIDs captured while still fresh.
    real_db.expire_all()
    refreshed_job = (await real_db.execute(select(Job).where(Job.id == job_id))).scalar_one()
    assert refreshed_job.status == "succeeded"
    assert refreshed_job.finished_at is not None

    refreshed_course = (
        await real_db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one()
    assert refreshed_course.status == "active"

    topic = (await real_db.execute(select(Topic).where(Topic.course_id == course_id))).scalar_one()
    assert topic.canonical_name == "Singleton pattern"
    assert (
        topic.aggregated_summary == "Singletons restrict instantiation to a single shared instance."
    )

    tags = list(
        (await real_db.execute(select(TopicTag).where(TopicTag.topic_id == topic.id))).scalars()
    )
    assert {t.name for t in tags} == {
        "explains the singleton pattern",
        "identifies its trade-offs",
        "spots misuse",
    }

    assert len(notifier.sent) == 1
    assert notifier.sent[0][1] == "learning.index_ready"


async def test_index_job_failure_reverts_course_status_and_records_error(
    real_db: AsyncSession, tmp_path: Path
) -> None:
    _cu, course, _section = await _seeded_course(
        real_db, tmp_path, "learning-index-fail@example.com"
    )
    course_id, user_id = course.id, course.user_id
    assert course.status == "draft"

    job = Job(course_id=course_id, user_id=user_id, kind="index_course")
    real_db.add(job)
    await real_db.commit()
    job_id = job.id

    fake_llm = FakeLLM()
    fake_llm.register_error("learning.align_topics", LLMRefused(category="policy"))
    platform = _platform(fake_llm, _RecordingNotifier())

    with pytest.raises(LLMRefused):
        await run_index_job_impl(platform, job_id)  # type: ignore[arg-type]

    real_db.expire_all()
    refreshed_job = (await real_db.execute(select(Job).where(Job.id == job_id))).scalar_one()
    assert refreshed_job.status == "failed"
    assert refreshed_job.error_code == "modules.learning.llm_refused"

    refreshed_course = (
        await real_db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one()
    assert refreshed_course.status == "draft"  # reverted to its pre-index status


async def test_reindex_preserves_stable_topic_and_its_score_history(
    real_db: AsyncSession, tmp_path: Path
) -> None:
    _cu, course, section = await _seeded_course(real_db, tmp_path, "learning-reindex@example.com")
    course_id, user_id, section_id = course.id, course.user_id, section.id

    alignment = TopicAlignment(
        topics=[
            AlignedTopic(
                name="Singleton pattern",
                description="Restricting a class to one instance.",
                member_section_ids=[section_id],
            )
        ],
        unmatched_section_ids=[],
    )

    async def _run_once() -> None:
        job = Job(course_id=course_id, user_id=user_id, kind="index_course")
        real_db.add(job)
        await real_db.commit()
        job_id = job.id
        fake_llm = FakeLLM()
        fake_llm.register("learning.align_topics", alignment)
        fake_llm.register("learning.generate_tags", TopicTags(names=["a", "b", "c"]))
        fake_llm.register("learning.summarize_topic", TopicSummary(summary="Summary."))
        await run_index_job_impl(_platform(fake_llm, _RecordingNotifier()), job_id)  # type: ignore[arg-type]

    await _run_once()
    real_db.expire_all()
    topic = (await real_db.execute(select(Topic).where(Topic.course_id == course_id))).scalar_one()
    topic_id = topic.id
    tag = (
        (await real_db.execute(select(TopicTag).where(TopicTag.topic_id == topic_id)))
        .scalars()
        .first()
    )
    assert tag is not None
    tag_id = tag.id

    # Simulate mastery history against this tag (Phase 5 writes this for
    # real; here it stands in for "history that must survive a re-index").
    score = TopicTagScore(topic_tag_id=tag_id, user_id=user_id, rolling_score=0.8)
    real_db.add(score)
    await real_db.commit()

    await _run_once()  # same topic name both runs -> matched, not recreated
    real_db.expire_all()

    topics = list(
        (await real_db.execute(select(Topic).where(Topic.course_id == course_id))).scalars()
    )
    assert len(topics) == 1
    assert topics[0].id == topic_id  # same row, not recreated

    surviving_score = (
        await real_db.execute(select(TopicTagScore).where(TopicTagScore.topic_tag_id == tag_id))
    ).scalar_one()
    assert surviving_score.rolling_score == 0.8


async def test_reindex_removing_a_topic_unanchors_its_notes(
    real_db: AsyncSession, tmp_path: Path
) -> None:
    _cu, course, section = await _seeded_course(
        real_db, tmp_path, "learning-reindex-remove@example.com"
    )
    course_id, user_id, section_id = course.id, course.user_id, section.id

    async def _run_with(alignment: TopicAlignment) -> None:
        job = Job(course_id=course_id, user_id=user_id, kind="index_course")
        real_db.add(job)
        await real_db.commit()
        job_id = job.id
        fake_llm = FakeLLM()
        fake_llm.register("learning.align_topics", alignment)
        fake_llm.register("learning.generate_tags", TopicTags(names=["a", "b", "c"]))
        fake_llm.register("learning.summarize_topic", TopicSummary(summary="Summary."))
        await run_index_job_impl(_platform(fake_llm, _RecordingNotifier()), job_id)  # type: ignore[arg-type]

    await _run_with(
        TopicAlignment(
            topics=[
                AlignedTopic(
                    name="Singleton pattern",
                    description="Restricting a class to one instance.",
                    member_section_ids=[section_id],
                )
            ],
            unmatched_section_ids=[],
        )
    )
    real_db.expire_all()
    topic = (await real_db.execute(select(Topic).where(Topic.course_id == course_id))).scalar_one()
    topic_id = topic.id

    note = Note(course_id=course_id, user_id=user_id, body="remember this", topic_id=topic_id)
    real_db.add(note)
    await real_db.commit()
    note_id = note.id

    # A second run whose alignment no longer produces "Singleton pattern" at
    # all — the old topic is removed rather than renamed in place.
    await _run_with(
        TopicAlignment(
            topics=[
                AlignedTopic(
                    name="Something unrelated",
                    description="A different topic entirely.",
                    member_section_ids=[section_id],
                )
            ],
            unmatched_section_ids=[],
        )
    )
    real_db.expire_all()

    topics = list(
        (await real_db.execute(select(Topic).where(Topic.course_id == course_id))).scalars()
    )
    assert [t.canonical_name for t in topics] == ["Something unrelated"]

    refreshed_note = (await real_db.execute(select(Note).where(Note.id == note_id))).scalar_one()
    assert refreshed_note.topic_id is None  # unanchored, not deleted (§8.5)
