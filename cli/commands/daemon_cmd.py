import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Manage the DevMemoryIndex background daemon.")


@app.command("start")
def start(
    jarvis: bool = typer.Option(
        False, "--jarvis",
        help="Enable wake word listener ('hey devmem'). Requires devmemory[jarvis].",
    ),
):
    """Start the daemon in the foreground (per-connector schedules from config)."""
    from daemon.scheduler import run_daemon
    run_daemon(jarvis=jarvis)


@app.command("stop")
def stop():
    """Stop a running foreground daemon (started with 'daemon start')."""
    import os
    import signal
    import subprocess

    result = subprocess.run(
        ["pgrep", "-f", "devmemory daemon start"],
        capture_output=True, text=True,
    )
    pids = [int(p) for p in result.stdout.split() if p.strip()]
    if not pids:
        console.print("[yellow]No running daemon found.[/yellow]")
        raise typer.Exit(0)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    console.print(f"[green]Sent SIGTERM to PID(s):[/green] {', '.join(str(p) for p in pids)}")


@app.command("install")
def install():
    """Install as a macOS launchd service (auto-starts at login)."""
    import platform
    if platform.system() != "Darwin":
        console.print("[red]launchd is macOS-only.[/red]")
        raise typer.Exit(1)
    try:
        from daemon.launchd import install as _install
        path = _install()
        console.print(f"[green]Installed and loaded:[/green] {path}")
        console.print("Daemon will start automatically at login and restart if it crashes.")
        console.print(f"Logs: [cyan]devmemory log[/cyan]")
    except Exception as e:
        console.print(f"[red]Install failed:[/red] {e}")
        raise typer.Exit(1)


@app.command("uninstall")
def uninstall():
    """Remove the launchd service."""
    import platform
    if platform.system() != "Darwin":
        console.print("[red]launchd is macOS-only.[/red]")
        raise typer.Exit(1)
    from daemon.launchd import uninstall as _uninstall, PLIST_PATH
    if _uninstall():
        console.print(f"[yellow]Unloaded and removed:[/yellow] {PLIST_PATH}")
    else:
        console.print("[yellow]Not installed — nothing to remove.[/yellow]")


@app.command("status")
def status():
    """Show whether the launchd service is installed and running."""
    import platform
    if platform.system() != "Darwin":
        console.print("[red]launchd is macOS-only.[/red]")
        raise typer.Exit(1)
    from daemon.launchd import status as _status
    from rich.table import Table
    s = _status()
    table = Table(title="Daemon Status")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Installed", "[green]yes[/green]" if s["installed"] else "[red]no[/red]")
    table.add_row("Running",   "[green]yes[/green]" if s["running"]   else "[red]no[/red]")
    table.add_row("PID",       str(s["pid"]) if s["pid"] else "—")
    table.add_row("Plist",     s["plist"])
    console.print(table)
