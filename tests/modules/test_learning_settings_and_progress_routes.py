"""M20 §21 (settings round-trip) and §15.2/§15.3 (progress/weak-points HTTP
wiring), plus §22's `PathItemCompleted` event, fired only by a completed
quiz (§3.5).
"""

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core import events as events_module
from disp.core.events import EventBus, set_event_bus
from disp.core.llm import FakeLLM
from disp.core.models import Setting
from disp.modules.learning.events import PathItemCompleted
from disp.modules.learning.llm_schemas import QuizDraft, QuizGrade, QuizQuestionDraft
from disp.modules.learning.models import (
    Course,
    PathItem,
    PathItemTopic,
    Source,
    SourceSection,
    Topic,
    TopicSourceSection,
    TopicTag,
)
from tests.factories import DEFAULT_PASSWORD, make_user


@pytest.fixture(autouse=True)
def _fresh_event_bus() -> Iterator[None]:
    previous = events_module._active_bus
    set_event_bus(EventBus())
    yield
    events_module._active_bus = previous


async def _authed(client: httpx.AsyncClient, db_session: AsyncSession, email: str) -> None:
    await make_user(db_session, email=email)
    await db_session.flush()
    await db_session.commit()
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


async def test_settings_round_trips_to_the_expected_key(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _authed(client, db_session, "learning-settings-roundtrip@example.com")

    put_resp = await client.put(
        "/api/settings/learning",
        json={"daily_study_reminder": True, "weak_point_threshold": 0.65},
    )
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()["daily_study_reminder"] is True

    row = (
        await db_session.execute(
            select(Setting).where(
                Setting.module_domain == "learning",
                Setting.key == "study.weak_point_threshold",
            )
        )
    ).scalar_one()
    assert row.value_json == 0.65
    # Pinned per §6.2's counterpart concern: a hand-constructed key string
    # in two places (settings_store's prefix-stripping and this test) must
    # not silently drift apart.
    assert row.is_secret is False


async def test_progress_and_weak_points_routes_through_http(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _authed(client, db_session, "learning-progress-http@example.com")

    create_course_resp = await client.post(
        "/api/learning/courses", json={"title": "Design Patterns"}
    )
    course_id = create_course_resp.json()["id"]
    course = (await db_session.execute(select(Course).where(Course.id == course_id))).scalar_one()

    source = Source(course_id=course.id, title="Notes", content_type="markdown", raw_text="x")
    db_session.add(source)
    await db_session.flush()
    section = SourceSection(
        source_id=source.id,
        heading_path="Ch 1",
        order_index=0,
        content_text="A singleton restricts a class to one instance.",
    )
    db_session.add(section)
    await db_session.flush()
    topic = Topic(course_id=course.id, canonical_name="Singleton", description="d")
    db_session.add(topic)
    await db_session.flush()
    db_session.add(TopicSourceSection(topic_id=topic.id, source_section_id=section.id))
    tag = TopicTag(topic_id=topic.id, name="explains the singleton pattern")
    db_session.add(tag)
    await db_session.flush()
    item = PathItem(
        course_id=course.id, tier="beginner", order_index=0, title="Lesson", status="approved"
    )
    db_session.add(item)
    await db_session.flush()
    db_session.add(PathItemTopic(path_item_id=item.id, topic_id=topic.id))
    await db_session.commit()

    progress_resp = await client.get(f"/api/learning/courses/{course_id}/progress")
    assert progress_resp.status_code == 200
    assert progress_resp.json() == {
        "completed": 0,
        "total": 1,
        "by_tier": {"beginner": {"total": 1, "completed": 0}},
    }

    weak_resp = await client.get(f"/api/learning/courses/{course_id}/weak-points")
    assert weak_resp.status_code == 200
    assert weak_resp.json() == []  # no attempts yet

    # Complete a quiz over the item and confirm PathItemCompleted fires with
    # the right score, and progress now reflects it.
    fake_llm = FakeLLM()
    fake_llm.register(
        "learning.generate_quiz",
        QuizDraft(
            questions=[
                QuizQuestionDraft(question_text="What is a singleton?", target_tag_ids=[tag.id])
            ]
        ),
    )
    monkeypatch.setattr(app.state.platform, "llm", fake_llm)

    received: list[PathItemCompleted] = []
    events_module._active_bus.subscribe(PathItemCompleted, received.append)  # type: ignore[union-attr]

    create_quiz_resp = await client.post(f"/api/learning/path-items/{item.id}/quizzes")
    session_id = create_quiz_resp.json()["id"]
    await client.post(f"/api/learning/quizzes/{session_id}/start")

    fake_llm.register(
        "learning.grade_quiz", QuizGrade(score=1.0, feedback_text="Correct!", tags_tested=[tag.id])
    )
    await client.post(
        f"/api/learning/quizzes/{session_id}/submit", json={"answer_text": "One instance."}
    )
    await client.post(f"/api/learning/quizzes/{session_id}/advance")

    for task in list(events_module._background_tasks):
        await task
    assert len(received) == 1
    assert received[0].score == 1.0
    assert received[0].path_item_id == item.id

    progress_after = await client.get(f"/api/learning/courses/{course_id}/progress")
    assert progress_after.json()["completed"] == 1
