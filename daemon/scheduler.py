import time
from datetime import date
from rich.console import Console
from connectors.registry import get_connectors
from core.config import get_connector_interval
from daemon.jobs.memory_cleanup import prune_memories
from daemon.jobs.dedup import dedup_memories

console = Console()

# Poll frequency: how often the loop wakes up to check connector due-times.
_POLL_INTERVAL = 60  # seconds


def run_daemon():
    """Run connectors on independent per-connector schedules.

    Each connector fires when `now - last_run >= configured_interval`.
    The loop wakes every 60 s to check — so the real granularity is ±60 s.
    """
    connectors = get_connectors()

    # Show effective intervals at startup
    console.print("[green]DevMemoryIndex daemon started[/green]")
    for c in connectors:
        interval = get_connector_interval(c.name)
        console.print(f"  [{c.name}] every {_fmt_interval(interval)}")

    last_run: dict[str, float] = {}  # connector name → last run timestamp
    last_prune_date = None
    last_dedup_date = None

    while True:
        now = time.time()

        for c in connectors:
            interval = get_connector_interval(c.name)
            due = now - last_run.get(c.name, 0) >= interval
            if not due:
                continue
            try:
                count = c.collect()
                if count > 0:
                    console.print(f"  [{c.name}] +{count} memories")
            except Exception as e:
                console.print(f"  [red][{c.name}] Error: {e}[/red]")
            last_run[c.name] = time.time()

        today = date.today()

        if last_prune_date != today:
            pruned = prune_memories()
            if pruned > 0:
                console.print(f"[dim]Pruned {pruned} underutilized memories[/dim]")
            last_prune_date = today

        # Dedup once per week (Monday)
        if today.weekday() == 0 and last_dedup_date != today:
            removed = dedup_memories()
            if removed > 0:
                console.print(f"[dim]Dedup removed {removed} duplicate memories[/dim]")
            last_dedup_date = today

        time.sleep(_POLL_INTERVAL)


def _fmt_interval(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m".rstrip(" 0m") or f"{seconds // 3600}h"
