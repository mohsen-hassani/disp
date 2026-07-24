from fastapi import FastAPI
from fastapi.testclient import TestClient

from disp.core.errors import AppError, register_exception_handlers


def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise AppError(
            status_code=404,
            code="notes.not_found",
            title="Not found",
            detail="The note does not exist.",
        )

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("something with a stack trace and secrets=hunter2")

    return app


def test_app_error_produces_problem_json() -> None:
    client = TestClient(_make_app(), raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "notes.not_found"
    assert body["status"] == 404
    assert body["detail"] == "The note does not exist."
    assert body["instance"] == "/boom"


def test_unhandled_exception_is_generic_500() -> None:
    client = TestClient(_make_app(), raise_server_exceptions=False)
    response = client.get("/crash")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "internal_error"
    assert body["detail"] == "An unexpected error occurred."
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text


def test_validation_error_has_errors_list() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/items/{item_id}")
    async def get_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/items/not-an-int")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert isinstance(body["errors"], list)
    assert len(body["errors"]) >= 1
