import typer
from rich.console import Console

console = Console()


def daemon():
    """Start background memory daemon (per-connector schedules from config)."""
    from daemon.scheduler import run_daemon
    run_daemon()
