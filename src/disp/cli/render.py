import json
import sys
from datetime import UTC, datetime
from typing import Any

from rich.console import Console

_stdout = Console()
_stderr = Console(stderr=True)


def configure(*, no_color: bool) -> None:
    global _stdout, _stderr
    _stdout = Console(no_color=no_color)
    _stderr = Console(stderr=True, no_color=no_color)


def out() -> Console:
    return _stdout


def err() -> Console:
    return _stderr


def emit_json(data: Any) -> None:
    sys.stdout.write(json.dumps(data, default=str) + "\n")


def humanize_relative(value: datetime) -> str:
    now = datetime.now(UTC)
    delta = now - value
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"
