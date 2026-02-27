import typer
from rich.console import Console

console = Console()


def daemon(
    interval: int = typer.Option(300, "--interval", "-i", help="Seconds between indexing runs"),
):
    """Start background memory daemon."""
    from daemon.scheduler import run_daemon
    console.print(f"[green]Starting daemon (interval: {interval}s)...[/green]")
    run_daemon(interval=interval)
