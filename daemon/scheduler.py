import time
from datetime import date
from rich.console import Console
from connectors.registry import get_connectors
from daemon.jobs.memory_cleanup import prune_memories

console = Console()


def run_daemon(interval: int = 300):
    """Run all connectors periodically. Prune underutilized memories once daily."""
    console.print(f"[green]DevMemoryIndex daemon started. Interval: {interval}s[/green]")

    last_prune_date = None

    while True:
        connectors = get_connectors()
        total = 0

        for c in connectors:
            try:
                count = c.collect()
                total += count
                if count > 0:
                    console.print(f"  [{c.name}] +{count} memories")
            except Exception as e:
                console.print(f"  [red][{c.name}] Error: {e}[/red]")

        if total > 0:
            console.print(f"[green]Cycle complete: +{total} new memories[/green]")

        today = date.today()
        if last_prune_date != today:
            pruned = prune_memories()
            if pruned > 0:
                console.print(f"[dim]Pruned {pruned} underutilized memories[/dim]")
            last_prune_date = today

        time.sleep(interval)
