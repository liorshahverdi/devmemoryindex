import json
import typer
from pathlib import Path
from datetime import datetime
from rich.console import Console
from core.store_provider import get_store
from core.schema import Memory
from core.embeddings import embed

console = Console()


def export(
    output: Path = typer.Argument(..., help="Output JSON file path"),
):
    """Export all memories to a JSON file."""
    store = get_store()
    records = store.get_all()
    data = [dict(r) for r in records]
    output.write_text(json.dumps(data, indent=2, default=str))
    console.print(f"[green]Exported {len(data)} memories → {output}[/green]")


def import_memories(
    input_file: Path = typer.Argument(..., help="JSON file to import"),
):
    """Import memories from a JSON file (skips duplicates)."""
    store = get_store()
    data = json.loads(input_file.read_text())
    added = 0
    for record in data:
        mem_id = record.get("id", "")
        if store.exists(mem_id):
            continue
        memory = Memory(
            id=mem_id,
            type=record.get("type", "agent_solution"),
            summary=record.get("summary", "")[:200],
            raw_text=record.get("raw_text", ""),
            source=record.get("source", "import"),
            repo=record.get("repo"),
            timestamp=datetime.fromisoformat(record["timestamp"]) if record.get("timestamp") else datetime.utcnow(),
            tags=record.get("tags", []),
            importance=record.get("importance", 0.5),
        )
        vector = embed(memory.summary)
        store.add(memory, vector)
        added += 1
    console.print(f"[green]Imported {added} new memories.[/green]")
