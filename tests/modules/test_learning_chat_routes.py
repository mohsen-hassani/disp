"""M20 §18.2/§18.4 (Phase 7): HTTP-level wiring for explain, chat, and notes.
Service-layer behavior is covered by `test_learning_chat.py`/
`test_learning_notes.py`; this proves the routes, DI, and schemas connect.
"""

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.llm import FakeLLM
from disp.modules.learning.models import Course, PathItem
from tests.factories import DEFAULT_PASSWORD, make_user


async def _authed(client: httpx.AsyncClient, db_session: AsyncSession, email: str) -> None:
    await make_user(db_session, email=email)
    await db_session.flush()
    await db_session.commit()
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


async def test_explain_and_chat_and_notes_through_http(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _authed(client, db_session, "learning-chat-http@example.com")

    create_course_resp = await client.post(
        "/api/learning/courses", json={"title": "Design Patterns"}
    )
    course_id = create_course_resp.json()["id"]

    course = (await db_session.execute(select(Course).where(Course.id == course_id))).scalar_one()
    item = PathItem(
        course_id=course.id, tier="beginner", order_index=0, title="Lesson", status="approved"
    )
    db_session.add(item)
    await db_session.commit()

    fake_llm = FakeLLM()
    monkeypatch.setattr(app.state.platform, "llm", fake_llm)

    fake_llm.register("learning.explain", "Here's an explanation.")
    explain_resp = await client.post(
        f"/api/learning/path-items/{item.id}/explain", json={"mode": "explain"}
    )
    assert explain_resp.status_code == 200, explain_resp.text
    assert explain_resp.json()["content"] == "Here's an explanation."

    create_chat_resp = await client.post(
        f"/api/learning/courses/{course_id}/chats",
        json={"scope_type": "path_item", "path_item_id": str(item.id)},
    )
    assert create_chat_resp.status_code == 201, create_chat_resp.text
    chat_id = create_chat_resp.json()["id"]

    list_chats_resp = await client.get(f"/api/learning/courses/{course_id}/chats")
    assert list_chats_resp.status_code == 200
    assert len(list_chats_resp.json()) == 1

    fake_llm.register("learning.chat", "Sure, here's the answer.")
    send_resp = await client.post(
        f"/api/learning/chats/{chat_id}/messages", json={"content": "Explain this."}
    )
    assert send_resp.status_code == 200, send_resp.text
    assert send_resp.json()["content"] == "Sure, here's the answer."

    messages_resp = await client.get(f"/api/learning/chats/{chat_id}/messages")
    assert messages_resp.status_code == 200
    assert len(messages_resp.json()) == 2

    create_note_resp = await client.post(
        f"/api/learning/courses/{course_id}/notes",
        json={"label": "todo", "body": "Come back to this"},
    )
    assert create_note_resp.status_code == 201, create_note_resp.text
    note_id = create_note_resp.json()["id"]

    list_notes_resp = await client.get(f"/api/learning/courses/{course_id}/notes")
    assert list_notes_resp.status_code == 200
    assert len(list_notes_resp.json()["items"]) == 1

    update_note_resp = await client.patch(
        f"/api/learning/notes/{note_id}", json={"body": "Updated body"}
    )
    assert update_note_resp.status_code == 200
    assert update_note_resp.json()["body"] == "Updated body"

    delete_note_resp = await client.delete(f"/api/learning/notes/{note_id}")
    assert delete_note_resp.status_code == 204
