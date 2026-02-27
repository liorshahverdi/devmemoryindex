import time
from datetime import date
from rich.console import Console
from connectors.registry import get_connectors
from core.config import get_connector_interval
from daemon.jobs.memory_cleanup import prune_memories
from daemon.jobs.dedup import dedup_memories
from daemon.watcher import start_watcher
import daemon.daemon_log as dlog

console = Console()

# Poll frequency: how often the loop wakes up to check connector due-times.
_POLL_INTERVAL = 60  # seconds


def _log(message: str, level: str = "INFO") -> None:
    """Write to log file and echo to terminal."""
    dlog.write(message, level)
    if level == "ERROR":
        console.print(f"[red]{message}[/red]")
    elif level == "WARN":
        console.print(f"[yellow]{message}[/yellow]")
    else:
        console.print(message)


def run_daemon():
    """Run connectors on independent per-connector schedules.

    Each connector fires when `now - last_run >= configured_interval`.
    The loop wakes every 60 s to check — so the real granularity is ±60 s.
    Logs are written to ~/.local/share/devmemory/daemon.log and trimmed daily.
    """
    connectors = get_connectors()

    # Trim on startup to handle any log growth since last run
    removed = dlog.trim()
    if removed:
        console.print(f"[dim]Log trimmed: removed {removed} old lines[/dim]")

    _log("DevMemoryIndex daemon started")
    for c in connectors:
        interval = get_connector_interval(c.name)
        _log(f"  [{c.name}] every {_fmt_interval(interval)}")

    # Start filesystem watcher in background thread
    start_watcher()

    last_run: dict[str, float] = {}  # connector name → last run timestamp
    last_prune_date = None
    last_dedup_date = None
    last_trim_date = None

    while True:
        now = time.time()

        for c in connectors:
            interval = get_connector_interval(c.name)
            if now - last_run.get(c.name, 0) < interval:
                continue
            try:
                count = c.collect()
                if count > 0:
                    _log(f"[{c.name}] +{count} memories")
            except Exception as e:
                _log(f"[{c.name}] Error: {e}", level="ERROR")
            last_run[c.name] = time.time()

        today = date.today()

        if last_prune_date != today:
            pruned = prune_memories()
            if pruned > 0:
                _log(f"Pruned {pruned} underutilized memories")
            last_prune_date = today

        # Dedup once per week (Monday)
        if today.weekday() == 0 and last_dedup_date != today:
            removed = dedup_memories()
            if removed > 0:
                _log(f"Dedup removed {removed} duplicate memories")
            last_dedup_date = today

        # Trim log once per day
        if last_trim_date != today:
            removed = dlog.trim()
            if removed:
                _log(f"Log trimmed: removed {removed} old lines")
            last_trim_date = today

        time.sleep(_POLL_INTERVAL)


def _fmt_interval(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m" if m else f"{h}h"
