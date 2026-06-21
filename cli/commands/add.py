import typer
import hashlib
from datetime import datetime
from core.store_provider import get_store
from core.schema import Memory
from core.embeddings import embed
from cli.commands._errors import exit_on_runtime_error

def add(
    summary: str = typer.Argument(..., help="Summary of the memory"),
    type: str = typer.Option("agent_solution", "--type", "-t"),
    repo: str | None = typer.Option(None, "--repo", "-r"),
    importance: float = typer.Option(0.9, "--importance", "-i"),
):
    """Manually add a memory (e.g., paste a Claude solution)."""
    try:
        store = get_store()
    except RuntimeError as exc:
        exit_on_runtime_error(exc)

    mem_id = hashlib.sha256(summary.encode()).hexdigest()
    memory = Memory(
        id=mem_id,
        type=type,
        summary=summary[:200],
        raw_text=summary,
        source="manual",
        repo=repo,
        timestamp=datetime.utcnow(),
        tags=["manual"],
        importance=importance,
    )

    try:
        vector = embed(memory.summary)
    except RuntimeError as exc:
        exit_on_runtime_error(exc)
    store.add(memory, vector)

    typer.echo(f"Memory added: {summary[:60]}...")