"""Shared CLI error handling helpers."""

import typer
from rich.console import Console
from typing import NoReturn

console = Console(stderr=True)


def exit_on_runtime_error(exc: RuntimeError) -> NoReturn:
    """Print an actionable RuntimeError without a Python traceback, then exit."""
    console.print("Error:", style="red", end=" ")
    console.print(str(exc), markup=False)
    raise typer.Exit(1) from exc
