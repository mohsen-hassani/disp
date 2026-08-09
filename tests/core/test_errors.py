import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from disp.core.errors import AppError, register_exception_handlers, validate_error_code


def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise AppError(
            status_code=404,
            code="modules.notes.not_found",
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
    assert body["code"] == "modules.notes.not_found"
    assert body["status"] == 404
    assert body["detail"] == "The note does not exist."
    assert body["instance"] == "/boom"


def test_unhandled_exception_is_generic_500() -> None:
    client = TestClient(_make_app(), raise_server_exceptions=False)
    response = client.get("/crash")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "core.platform.internal_error"
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
    assert body["code"] == "core.platform.validation_error"
    assert isinstance(body["errors"], list)
    assert len(body["errors"]) >= 1


@pytest.mark.parametrize(
    "code",
    [
        "notes.not_found",  # the pre-M21 two-segment shape
        "auth.token_expired",
        "internal_error",  # the pre-M21 bare shape
        "core.files.too_large.extra",  # four segments
        "plugins.notes.not_found",  # realm is core|modules, nothing else
        "core.Notes.not_found",  # uppercase
        "core..not_found",  # empty segment
    ],
)
def test_malformed_error_codes_are_rejected(code: str) -> None:
    """The registry in PLATFORM-SPEC Appendix A is only as good as its enforcement.

    Before M21 `AppError.code` was an unvalidated `str`, which is how three
    different code shapes coexisted and how a proposed milestone reached for a
    fourth without anyone noticing. Failing at construction means a bad code
    breaks the test that raises it, not a client parsing the response.
    """
    with pytest.raises(ValueError, match="three segments"):
        validate_error_code(code)

    with pytest.raises(ValueError, match="three segments"):
        AppError(status_code=400, code=code, title="Bad", detail="Bad.")


def test_well_formed_error_codes_are_accepted() -> None:
    for code in (
        "core.auth.token_expired",
        "core.platform.rate_limited",
        "modules.notes.not_found",
    ):
        assert validate_error_code(code) == code
