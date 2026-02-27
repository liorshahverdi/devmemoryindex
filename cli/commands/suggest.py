import subprocess
import typer
from rich.console import Console
from core.store_provider import get_store
from core.embeddings import embed
from core.context_engine import ContextEngine

console = Console()


def _diff_to_query(diff: str) -> str:
    """Extract a meaningful search query from a git diff."""
    lines = diff.splitlines()
    files = [l[6:] for l in lines if l.startswith("+++ b/")]
    added = [l[1:].strip() for l in lines if l.startswith("+") and not l.startswith("+++") and l[1:].strip()]

    parts = []
    if files:
        parts.append("Files: " + ", ".join(files[:5]))
    if added:
        parts.append("Changes: " + " ".join(added[:40]))

    return " ".join(parts)[:600]


def suggest(
    staged: bool = typer.Option(False, "--staged", help="Use staged changes (git diff --cached)"),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Filter by repo"),
    tokens: int = typer.Option(4000, "--tokens", help="Max token budget"),
    format: str = typer.Option(
        "markdown", "--format", "-f", help="Output format: raw, markdown, claude"
    ),
    copy: bool = typer.Option(False, "--copy", help="Copy context to clipboard"),
):
    """Suggest relevant memories based on your current git changes."""
    cmd = ["git", "diff", "--cached"] if staged else ["git", "diff", "HEAD"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    diff = proc.stdout.strip()

    if diff:
        query = _diff_to_query(diff)
        source = "staged diff" if staged else "working tree diff"
    else:
        # Fallback: use recent commit messages as query
        proc = subprocess.run(
            ["git", "log", "-5", "--pretty=%s"],
            capture_output=True, text=True,
        )
        query = proc.stdout.strip().replace("\n", " ")
        if not query:
            console.print("[yellow]No git changes or recent commits found.[/yellow]")
            raise typer.Exit()
        source = "recent commits (no diff found)"

    console.print(f"[dim]Source: {source}[/dim]")
    short_query = query[:100] + "..." if len(query) > 100 else query
    console.print(f"[dim]Query: {short_query}[/dim]\n")

    store = get_store()
    engine = ContextEngine(store)
    vector = embed(query)

    result = engine.build(
        query=query,
        vector=vector,
        repo=repo,
        max_tokens=tokens,
        format=format,
    )

    if result["memory_count"] == 0:
        console.print("[yellow]No relevant memories found.[/yellow]")
        raise typer.Exit()

    console.print(result["context_text"])

    if copy:
        try:
            subprocess.run(
                ["pbcopy"],
                input=result["context_text"].encode(),
                check=True,
            )
            console.print("\n[green]Copied to clipboard.[/green]")
        except Exception:
            console.print("\n[yellow]Could not copy to clipboard.[/yellow]")

    console.print(
        f"\n[dim]{result['memory_count']} memories · "
        f"~{result['token_estimate']} tokens[/dim]"
    )
