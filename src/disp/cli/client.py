import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

from disp import __version__

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_TOKEN_NAME_LEN = 64


class CliError(Exception):
    """Base for every error the CLI maps to a specific exit code (§19.3)."""

    def __init__(self, message: str, *, exit_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


class AuthError(CliError):
    def __init__(self, message: str = "Not logged in or token revoked — run `disp login`") -> None:
        super().__init__(message, exit_code=3)


class ConfigCliError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=3)


class CliPermissionError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=1)


class NotFoundError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=6)


class ServerError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=5)


class NetworkError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=4)


class RateLimitedError(CliError):
    def __init__(self, message: str = "Rate limited. Please try again later.") -> None:
        super().__init__(message, exit_code=1)


@dataclass
class ClientConfig:
    server: str
    token: str | None
    verbose: bool = False


def _problem_detail(response: httpx.Response, fallback: str) -> str:
    try:
        data = response.json()
    except ValueError:
        return fallback
    detail = data.get("detail") if isinstance(data, dict) else None
    return str(detail) if detail else fallback


class ApiClient:
    def __init__(
        self, config: ClientConfig, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        # `transport` is a testing seam only (§22.1 requires CLI tests to hit
        # the real app in-process rather than a real network port); normal
        # CLI usage never passes it, leaving httpx's default transport in
        # place.
        self._config = config
        headers = {"User-Agent": f"disp-cli/{__version__}"}
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"
        self._http = httpx.Client(
            base_url=config.server,
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=False,
            headers=headers,
            transport=transport,
        )

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        start = time.perf_counter()
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise NetworkError(f"Could not reach {self._config.server}: {exc}") from exc
        if self._config.verbose:
            duration_ms = (time.perf_counter() - start) * 1000
            print(
                f"{method} {path} -> {response.status_code} ({duration_ms:.0f}ms)",
                file=sys.stderr,
            )
        return response

    def request(
        self,
        method: str,
        path: str,
        *,
        raise_for_status: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        response = self._send(method, path, **kwargs)

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    time.sleep(float(retry_after))
                except ValueError:
                    pass
            response = self._send(method, path, **kwargs)
            if response.status_code == 429:
                raise RateLimitedError(_problem_detail(response, "Rate limited."))

        if raise_for_status:
            self.raise_for_status(response)
        return response

    def raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        message = _problem_detail(response, f"Request failed with status {status}.")
        if status == 401:
            raise AuthError()
        if status == 403:
            raise CliPermissionError(message)
        if status == 404:
            raise NotFoundError(message)
        if status >= 500:
            raise ServerError(message)
        raise CliError(message, exit_code=1)
