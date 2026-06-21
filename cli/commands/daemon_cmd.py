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
def install(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the service definition without writing files or enabling it.",
    ),
):
    """Install as a native user service (systemd on Linux, launchd on macOS)."""
    import platform
    system = platform.system()
    try:
        if system == "Darwin":
            from daemon.launchd import install as _install
            result = _install(dry_run=dry_run)
            if dry_run:
                console.print(result)
                return
            console.print(f"[green]Installed and loaded:[/green] {result}")
        elif system == "Linux":
            from daemon.systemd import install as _install
            result = _install(dry_run=dry_run)
            if dry_run:
                console.print(result)
                return
            console.print(f"[green]Installed and enabled:[/green] {result}")
        else:
            console.print(f"[red]Unsupported daemon platform:[/red] {system}")
            raise typer.Exit(1)
        console.print("Daemon will start automatically and restart if it crashes.")
        console.print("Logs: [cyan]devmemory log[/cyan]")
    except Exception as e:
        console.print(f"[red]Install failed:[/red] {e}")
        raise typer.Exit(1)


@app.command("uninstall")
def uninstall():
    """Remove the native user service."""
    import platform
    system = platform.system()
    if system == "Darwin":
        from daemon.launchd import uninstall as _uninstall, PLIST_PATH
        if _uninstall():
            console.print(f"[yellow]Unloaded and removed:[/yellow] {PLIST_PATH}")
        else:
            console.print("[yellow]Not installed — nothing to remove.[/yellow]")
    elif system == "Linux":
        from daemon.systemd import uninstall as _uninstall, SERVICE_PATH
        try:
            if _uninstall():
                console.print(f"[yellow]Disabled and removed:[/yellow] {SERVICE_PATH}")
            else:
                console.print("[yellow]Not installed — nothing to remove.[/yellow]")
        except Exception as e:
            console.print(f"[red]Uninstall failed:[/red] {e}")
            raise typer.Exit(1)
    else:
        console.print(f"[red]Unsupported daemon platform:[/red] {system}")
        raise typer.Exit(1)


@app.command("status")
def status():
    """Show whether the native user service is installed and running."""
    import platform
    from rich.table import Table

    system = platform.system()
    if system == "Darwin":
        from daemon.launchd import status as _status
        s = _status()
        location_label = "Plist"
        location_value = s["plist"]
    elif system == "Linux":
        from daemon.systemd import status as _status
        s = _status()
        location_label = "Service"
        location_value = s["service"]
    else:
        console.print(f"[red]Unsupported daemon platform:[/red] {system}")
        raise typer.Exit(1)

    table = Table(title="Daemon Status")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Backend", "systemd --user" if system == "Linux" else "launchd")
    table.add_row("Installed", "[green]yes[/green]" if s["installed"] else "[red]no[/red]")
    table.add_row("Running",   "[green]yes[/green]" if s["running"]   else "[red]no[/red]")
    if system == "Darwin":
        table.add_row("PID", str(s["pid"]) if s["pid"] else "—")
    else:
        table.add_row("Active State", s["active_state"])
    table.add_row(location_label, location_value)
    console.print(table)
