import typer
from rich.console import Console

from connectors.graphify_connector import GraphifyConnector, GraphifyOutputMissingError

app = typer.Typer(help="Import optional Graphify code graph outputs.")
console = Console()


def _format_stats(stats: dict) -> str:
    skipped = stats.get("skipped", {}) or {}
    skipped_text = ", ".join(f"{key}={value}" for key, value in sorted(skipped.items())) or "none"
    dry_run = " dry_run=true" if stats.get("dry_run") else ""
    return (
        f"repo={stats.get('repo')}, reports={stats.get('reports', 0)}, "
        f"nodes={stats.get('nodes', 0)}, edges={stats.get('edges', 0)}, skipped: {skipped_text}, "
        f"errors={stats.get('errors', 0)}{dry_run}"
    )


@app.command("ingest")
def ingest_graphify(
    path: str = typer.Argument(".", help="Repository or directory containing graphify-out/."),
    repo: str | None = typer.Option(None, "--repo", help="Override repo name stored on imported memories."),
    graph: str | None = typer.Option(None, "--graph", help="Path to graph.json. Defaults to PATH/graphify-out/graph.json."),
    report: str | None = typer.Option(None, "--report", help="Path to GRAPH_REPORT.md. Defaults to PATH/graphify-out/GRAPH_REPORT.md."),
    no_report: bool = typer.Option(False, "--no-report", help="Skip GRAPH_REPORT.md ingestion."),
    no_nodes: bool = typer.Option(False, "--no-nodes", help="Skip graph.json node ingestion."),
    min_degree: int = typer.Option(0, "--min-degree", min=0, help="Only ingest graph nodes with degree >= N."),
    with_edges: bool = typer.Option(False, "--with-edges", help="Store graph.json edges in EdgeStore between imported graphify_node memories."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show import counts without embedding or writing memories."),
):
    """Import an existing Graphify graphify-out directory."""
    connector = GraphifyConnector(
        path=path,
        repo=repo,
        graph=graph,
        report=report,
        no_report=no_report,
        no_nodes=no_nodes,
        min_degree=min_degree,
        with_edges=with_edges,
        dry_run=dry_run,
    )
    try:
        count = connector.collect()
    except GraphifyOutputMissingError as exc:
        console.print(f"[graphify] {exc}", markup=False)
        raise typer.Exit(1) from exc
    except ValueError as exc:
        console.print(f"[graphify] {exc}", markup=False)
        raise typer.Exit(1) from exc

    if dry_run:
        console.print(f"[graphify] Dry run: {count} memories would be imported", markup=False)
    else:
        console.print(f"[graphify] +{count} memories", markup=False)
    console.print(f"[graphify] {_format_stats(connector.serializable_stats())}", markup=False)
