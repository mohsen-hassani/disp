import functools
from collections.abc import Callable
from typing import Any

import typer

from disp.cli import render
from disp.cli.client import CliError
from disp.cli.state import CliState


def handle_cli_errors[F: Callable[..., Any]](func: F) -> F:
    """Every command function MUST declare a `ctx: typer.Context` parameter
    (Click/Typer always passes it as the keyword `ctx`, regardless of
    position). Converts CliError subclasses into the documented exit code
    (§19.3) and never lets an unexpected exception show a traceback unless
    `--verbose` was passed (§19.5)."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx = kwargs.get("ctx")
        state: CliState | None = getattr(ctx, "obj", None)
        verbose = bool(state.verbose) if state is not None else False

        try:
            return func(*args, **kwargs)
        except typer.Exit:
            raise
        except CliError as exc:
            render.err().print(f"[red]Error:[/red] {exc.message}")
            raise typer.Exit(code=exc.exit_code) from None
        except Exception as exc:
            if verbose:
                raise
            render.err().print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from None

    return wrapper  # type: ignore[return-value]
