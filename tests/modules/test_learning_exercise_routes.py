"""M20 §18.3 (Phase 6): HTTP-level wiring for the exercise routes, plus the
rubric-leak test §12 calls out explicitly: `internal_rubric` must appear in
neither a serialized response nor the generated OpenAPI schema. Checking one
handler's output would pass while a later `include_in_schema` change leaked
it silently — the OpenAPI dump is what actually proves the wire contract.
"""

import json

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.llm import FakeLLM
from disp.modules.learning.llm_schemas import (
    ExerciseDraft,
    ExerciseGrade,
    ExerciseStepDraft,
)
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
from disp.modules.learning.schemas import ExerciseItemOut, ExerciseSessionOut
from tests.factories import DEFAULT_PASSWORD, make_user

_RUBRIC_SENTINEL = "SENTINEL-RUBRIC-must-prevent-more-than-one-instance-1234"


async def _authed(client: httpx.AsyncClient, db_session: AsyncSession, email: str) -> None:
    await make_user(db_session, email=email)
    await db_session.flush()
    await db_session.commit()
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


async def _seed_approved_item(db_session: AsyncSession, course_id: str) -> tuple[str, str]:
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
    return str(item.id), str(tag.id)


async def test_exercise_happy_path_through_http(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _authed(client, db_session, "learning-exercise-http@example.com")
    create_course_resp = await client.post(
        "/api/learning/courses", json={"title": "Design Patterns"}
    )
    item_id, tag_id = await _seed_approved_item(db_session, create_course_resp.json()["id"])

    fake_llm = FakeLLM()
    fake_llm.register(
        "learning.generate_exercise",
        ExerciseDraft(
            steps=[
                ExerciseStepDraft(
                    instruction_text="Implement a singleton.",
                    hint_text="Use a class-level instance.",
                    internal_rubric=_RUBRIC_SENTINEL,
                    target_tag_ids=[tag_id],
                )
            ]
        ),
    )
    monkeypatch.setattr(app.state.platform, "llm", fake_llm)

    create_resp = await client.post(f"/api/learning/path-items/{item_id}/exercises")
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["status"] == "draft"
    assert len(body["steps"]) == 1
    assert _RUBRIC_SENTINEL not in create_resp.text
    session_id = body["id"]
    step_id = body["steps"][0]["id"]
    assert "internal_rubric" not in body["steps"][0]

    start_resp = await client.post(f"/api/learning/exercises/{session_id}/start")
    assert start_resp.status_code == 200

    current_resp = await client.get(f"/api/learning/exercises/{session_id}/current")
    assert current_resp.status_code == 200
    assert current_resp.json()["id"] == step_id
    assert _RUBRIC_SENTINEL not in current_resp.text

    fake_llm.register(
        "learning.grade_exercise",
        ExerciseGrade(passed=True, feedback_text="Nicely done.", tags_tested=[tag_id]),
    )
    submit_resp = await client.post(
        f"/api/learning/exercises/{session_id}/submit",
        json={"submission_text": "class Singleton: _instance = None"},
    )
    assert submit_resp.status_code == 200, submit_resp.text
    assert submit_resp.json()["passed"] is True
    assert _RUBRIC_SENTINEL not in submit_resp.text

    advance_resp = await client.post(f"/api/learning/exercises/{session_id}/advance")
    assert advance_resp.status_code == 200
    assert advance_resp.json()["status"] == "completed"

    summary_resp = await client.get(f"/api/learning/exercises/{session_id}/summary")
    assert summary_resp.status_code == 200
    assert summary_resp.json()["pass_rate"] == 1.0
    assert _RUBRIC_SENTINEL not in summary_resp.text

    # §3.5: exercise completion never drives path-item completion_status.
    refreshed_item = await db_session.get(PathItem, item_id)
    assert refreshed_item is not None
    assert refreshed_item.completion_status == "not_started"


def test_exercise_wire_schemas_have_no_rubric_field() -> None:
    assert "internal_rubric" not in ExerciseItemOut.model_fields
    assert "internal_rubric" not in ExerciseSessionOut.model_fields


def test_openapi_schema_never_mentions_internal_rubric(app: FastAPI) -> None:
    # The OpenAPI dump is the actual wire contract — checking only one
    # handler's serialized output would pass against a later
    # `include_in_schema` regression that this catches.
    schema_text = json.dumps(app.openapi())
    assert "internal_rubric" not in schema_text
