"""devmemory graph — visualize typed memory relationships."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

console = Console()


def get_store():
    """Load the memory store lazily so base CLI help stays lightweight."""
    from core.store_provider import get_store as _get_store

    return _get_store()


def get_edges():
    """Load the edge store lazily so importing cli.main does not require LanceDB."""
    from core.edge_provider import get_edges as _get_edges

    return _get_edges()


def graph(
    memory_id: str = typer.Argument(..., help="Root memory ID or unique prefix"),
    depth: int = typer.Option(2, "--depth", "-d", min=1, help="Relationship depth to traverse"),
) -> None:
    """Show the typed relationship graph around a memory."""
    store = get_store()
    root_record = _get_memory(store, memory_id)
    if root_record is None:
        console.print(f"[red]No memory found with ID or prefix:[/red] {memory_id}")
        raise typer.Exit(1)

    root_id = root_record.get("id", memory_id)
    edge_store = get_edges()
    graph_data = edge_store.get_graph(root_id, depth=depth)
    edges = graph_data.get("edges") or []

    node_ids = _collect_node_ids(root_id, graph_data)
    records = {root_id: root_record}
    for node_id in node_ids:
        if node_id == root_id:
            continue
        record = _get_memory(store, node_id)
        if record is not None:
            records[node_id] = record

    console.print(Panel(_node_label(root_id, records.get(root_id)), title="[bold]Memory Graph[/bold]", border_style="cyan"))

    if not edges:
        console.print("[yellow]No relationships found.[/yellow]")
        return

    tree = Tree(_node_label(root_id, records.get(root_id)))
    adjacency = _build_adjacency(edges)
    _add_children(tree, root_id, adjacency, records, visited={root_id})
    console.print(tree)
    console.print()
    _print_edge_table(edges, records)


def _get_memory(store: Any, memory_id: str) -> dict | None:
    try:
        return store.get_by_id(memory_id, reinforce=False)
    except TypeError:
        return store.get_by_id(memory_id)


def _collect_node_ids(root_id: str, graph_data: dict) -> set[str]:
    node_ids = {root_id}
    node_ids.update(graph_data.get("nodes") or [])
    for edge in graph_data.get("edges") or []:
        if edge.get("from_id"):
            node_ids.add(edge["from_id"])
        if edge.get("to_id"):
            node_ids.add(edge["to_id"])
    return node_ids


def _build_adjacency(edges: list[dict]) -> dict[str, list[tuple[str, str, str, float | None]]]:
    adjacency: dict[str, list[tuple[str, str, str, float | None]]] = defaultdict(list)
    for edge in edges:
        from_id = edge.get("from_id")
        to_id = edge.get("to_id")
        edge_type = edge.get("edge_type", "related_to")
        confidence = edge.get("confidence")
        if not from_id or not to_id:
            continue
        adjacency[from_id].append((to_id, "→", edge_type, confidence))
        adjacency[to_id].append((from_id, "←", edge_type, confidence))
    return adjacency


def _add_children(
    tree: Tree,
    node_id: str,
    adjacency: dict[str, list[tuple[str, str, str, float | None]]],
    records: dict[str, dict],
    visited: set[str],
) -> None:
    for neighbor_id, direction, edge_type, confidence in adjacency.get(node_id, []):
        if neighbor_id in visited:
            continue
        edge_label = f"[bold magenta]{direction} {edge_type}[/bold magenta]"
        if confidence is not None:
            edge_label += f" [dim]({float(confidence):.2f})[/dim]"
        branch = tree.add(f"{edge_label}  {_node_label(neighbor_id, records.get(neighbor_id))}")
        visited.add(neighbor_id)
        _add_children(branch, neighbor_id, adjacency, records, visited)


def _print_edge_table(edges: list[dict], records: dict[str, dict]) -> None:
    table = Table("From", "Type", "To", "Confidence", box=box.SIMPLE, header_style="bold cyan")
    for edge in edges:
        confidence = edge.get("confidence")
        table.add_row(
            _short_label(edge.get("from_id", ""), records.get(edge.get("from_id", ""))),
            edge.get("edge_type", ""),
            _short_label(edge.get("to_id", ""), records.get(edge.get("to_id", ""))),
            "" if confidence is None else f"{float(confidence):.2f}",
        )
    console.print(table)


def _node_label(memory_id: str, record: dict | None) -> str:
    short_id = memory_id[:12]
    if record is None:
        return f"[dim]{short_id}[/dim] [red]missing memory[/red]"
    mem_type = record.get("type") or "memory"
    repo = record.get("repo") or "—"
    summary = record.get("summary") or record.get("raw_text") or "(no summary)"
    return f"[bold]{summary}[/bold] [dim]({short_id}, {mem_type}, {repo})[/dim]"


def _short_label(memory_id: str, record: dict | None) -> str:
    if record is None:
        return memory_id[:12]
    return f"{memory_id[:12]} {record.get('summary', '')[:48]}"
