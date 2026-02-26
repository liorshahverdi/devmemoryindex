import typer
from rich.console import Console
from daemon.jobs.memory_cleanup import prune_memories, PRUNE_IMPORTANCE_FLOOR, PRUNE_MAX_AGE_DAYS

console = Console()


def prune(
    importance_floor: float = typer.Option(
        PRUNE_IMPORTANCE_FLOOR, "--floor", "-f",
        help="Delete memories with importance below this threshold",
    ),
    max_age_days: int = typer.Option(
        PRUNE_MAX_AGE_DAYS, "--age", "-a",
        help="Delete memories older than N days with low importance",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Preview deletions without removing anything",
    ),
):
    """Remove underutilized memories to reclaim database space."""
    count = prune_memories(
        importance_floor=importance_floor,
        max_age_days=max_age_days,
        dry_run=dry_run,
    )
    label = "Would delete" if dry_run else "Deleted"
    color = "yellow" if dry_run else "green"
    console.print(f"[{color}]{label} {count} memories.[/{color}]")
