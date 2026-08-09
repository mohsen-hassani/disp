import re
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = structlog.get_logger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"

# Every `code` in a problem response is "<realm>.<subsystem>.<error>": realm is
# `core` for anything the backbone owns and `modules` for anything a module
# owns. Three segments, always.
#
# Deliberately NOT contract.KEY_RE, which is the *other* dotted namespace in
# this platform (tile keys, job names, notification types) and has exactly two
# segments. The two used to be indistinguishable on sight — "notes.not_found"
# an error, "notes.latest" a tile key — and the ambiguity is why a proposed
# milestone reached for a third shape ("core.files.too_large") without anyone
# noticing it matched neither. Segment count now tells them apart.
#
# Enforced at construction rather than at response time so a bad code fails in
# the test that raises it, not in front of a client.
ERROR_CODE_RE = re.compile(r"^(core|modules)\.[a-z][a-z0-9_]{1,31}\.[a-z][a-z0-9_]{1,63}$")


def validate_error_code(code: str) -> str:
    if not ERROR_CODE_RE.match(code):
        raise ValueError(
            f"error code {code!r} must be '<core|modules>.<subsystem>.<error>' "
            f"(three segments, matching {ERROR_CODE_RE.pattern})"
        )
    return code


# Shared across app.py (SlowAPIMiddleware + app.state.limiter) and any router
# that needs a `@limiter.limit(...)` decorator. Toggled on/off at startup via
# `limiter.enabled = settings.rate_limit_enabled`.
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])


class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str | None = None
    code: str
    request_id: str | None = None
    errors: list[dict[str, Any]] | None = None


class AppError(Exception):
    """Base class for all application errors carrying an RFC 9457 problem shape."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        title: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = validate_error_code(code)
        self.title = title
        self.detail = detail
        self.headers = headers


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def problem_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    problem = ProblemDetail(
        title=title,
        status=status_code,
        detail=detail,
        instance=request.url.path,
        code=validate_error_code(code),
        request_id=_request_id(request),
        errors=errors,
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return problem_response(
            request,
            status_code=422,
            code="core.platform.validation_error",
            title="Validation error",
            detail="The request did not match the expected schema.",
            errors=errors,
        )

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        headers = dict(exc.headers) if exc.headers else None
        return problem_response(
            request,
            status_code=exc.status_code,
            code="core.platform.http_error",
            title=str(exc.detail) if exc.detail else "HTTP error",
            detail=str(exc.detail) if exc.detail else "An HTTP error occurred.",
            headers=headers,
        )

    @app.exception_handler(RateLimitExceeded)
    async def _handle_rate_limit(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        retry_after = str(getattr(exc, "retry_after", 60))
        return problem_response(
            request,
            status_code=429,
            code="core.platform.rate_limited",
            title="Rate limited",
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": retry_after},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            request_id=_request_id(request),
            path=request.url.path,
            exc_info=exc,
        )
        return problem_response(
            request,
            status_code=500,
            code="core.platform.internal_error",
            title="Internal server error",
            detail="An unexpected error occurred.",
        )
