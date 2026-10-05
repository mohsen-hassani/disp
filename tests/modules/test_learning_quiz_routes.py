"""M20 §18.3 (Phase 5): HTTP-level wiring for the quiz routes.

The service-layer parametrized suite (`test_learning_sessions.py`) is where
the state-machine invariants are proven; this file exists to prove the
HTTP wiring itself — dependency injection (`_get_llm`), route paths,
request/response schemas — works end to end through a real request.
`app.state.platform.llm` is swapped to a `FakeLLM` for the duration of each
test via `monkeypatch`, which reverts automatically at test end.
"""

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.llm import FakeLLM
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


async def _authed(client: httpx.AsyncClient, db_session: AsyncSession, email: str) -> None:
    await make_user(db_session, email=email)
    await db_session.flush()
    await db_session.commit()
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


async def test_quiz_happy_path_through_http(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _authed(client, db_session, "learning-quiz-http@example.com")

    create_course_resp = await client.post(
        "/api/learning/courses", json={"title": "Design Patterns"}
    )
    assert create_course_resp.status_code == 201
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

    create_resp = await client.post(f"/api/learning/path-items/{item.id}/quizzes")
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["status"] == "draft"
    assert len(body["questions"]) == 1
    session_id = body["id"]
    question_id = body["questions"][0]["id"]

    get_resp = await client.get(f"/api/learning/quizzes/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["questions"][0]["id"] == question_id

    start_resp = await client.post(f"/api/learning/quizzes/{session_id}/start")
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "in_progress"

    current_resp = await client.get(f"/api/learning/quizzes/{session_id}/current")
    assert current_resp.status_code == 200
    assert current_resp.json()["id"] == question_id

    fake_llm.register(
        "learning.grade_quiz",
        QuizGrade(score=1.0, feedback_text="Correct!", tags_tested=[tag.id]),
    )
    submit_resp = await client.post(
        f"/api/learning/quizzes/{session_id}/submit", json={"answer_text": "One instance only."}
    )
    assert submit_resp.status_code == 200, submit_resp.text
    assert submit_resp.json()["score"] == 1.0

    advance_resp = await client.post(f"/api/learning/quizzes/{session_id}/advance")
    assert advance_resp.status_code == 200
    assert advance_resp.json()["status"] == "completed"

    summary_resp = await client.get(f"/api/learning/quizzes/{session_id}/summary")
    assert summary_resp.status_code == 200
    assert summary_resp.json()["overall_score"] == 1.0
    assert summary_resp.json()["question_count"] == 1


async def test_quiz_create_without_approved_path_item_conflicts(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _authed(client, db_session, "learning-quiz-draft-http@example.com")

    create_course_resp = await client.post("/api/learning/courses", json={"title": "Draft Course"})
    course_id = create_course_resp.json()["id"]
    item = PathItem(course_id=course_id, tier="beginner", order_index=0, title="Lesson")
    db_session.add(item)
    await db_session.commit()

    monkeypatch.setattr(app.state.platform, "llm", FakeLLM())
    resp = await client.post(f"/api/learning/path-items/{item.id}/quizzes")
    assert resp.status_code == 409
    assert resp.json()["code"] == "modules.learning.path_not_approved"
