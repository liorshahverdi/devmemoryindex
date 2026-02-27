import typer
from rich.console import Console
import daemon.daemon_log as dlog

console = Console()


def log(
    lines: int = typer.Option(50, "--lines", "-n", help="Number of recent lines to show"),
    path: bool = typer.Option(False, "--path", help="Print log file path and exit"),
):
    """Show recent daemon log entries."""
    if path:
        console.print(str(dlog.LOG_PATH))
        return

    entries = dlog.tail(lines)
    if not entries:
        console.print(f"[dim]No log entries yet. Log will be written to:[/dim] {dlog.LOG_PATH}")
        return

    for line in entries:
        # Colour by level
        if " [ERROR] " in line:
            console.print(f"[red]{line}[/red]")
        elif " [WARN] " in line:
            console.print(f"[yellow]{line}[/yellow]")
        else:
            console.print(f"[dim]{line[:19]}[/dim] {line[20:]}")
