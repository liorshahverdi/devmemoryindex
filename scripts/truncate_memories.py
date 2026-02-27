"""CLI to truncate memories in the LanceDB store.

Usage examples:
  # dry-run: show how many would be deleted
  python scripts/truncate_memories.py --dry-run

  # actually delete all records
  python scripts/truncate_memories.py --yes

  # dry-run for repo 'test'
  python scripts/truncate_memories.py --filter-repo test --dry-run

"""
import typer
from rich.console import Console
from core.memory_store import MemoryStore

console = Console()
app = typer.Typer()


@app.command()
def main(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview deletions without removing anything"),
    yes: bool = typer.Option(False, "--yes", help="Actually perform deletions (required to delete)"),
    filter_repo: str | None = typer.Option(None, "--filter-repo", help="Only delete records with this repo value"),
    db_path: str = typer.Option("./memory_db", "--db-path", help="Path to LanceDB directory"),
):
    store = MemoryStore(db_path)
    count = store.truncate(dry_run=True, filter_repo=filter_repo)

    if dry_run and yes:
        console.print("[yellow]Warning: both --dry-run and --yes passed. Doing dry-run.[/yellow]")

    if dry_run:
        console.print(f"[yellow]Dry-run: {count} records would be deleted.[/yellow]")
        return

    if not yes:
        console.print("[red]Refusing to delete: pass --yes to confirm.[/red]")
        return

    deleted = store.truncate(dry_run=False, filter_repo=filter_repo)
    console.print(f"[green]Deleted {deleted} records.[/green]")


if __name__ == "__main__":
    app()
