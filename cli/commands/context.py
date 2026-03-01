import typer
import json
import subprocess
from rich.console import Console
from rich.markdown import Markdown
from core.store_provider import get_store
from core.embeddings import embed
from core.context_engine import ContextEngine

console = Console()


def context(
    query: str = typer.Argument(..., help="What context do you need?"),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Filter by repo"),
    tokens: int = typer.Option(4000, "--tokens", help="Max token budget"),
    format: str = typer.Option(
        "markdown", "--format", "-f", help="Output format: raw, markdown, claude"
    ),
    as_json: bool = typer.Option(False, "--json", help="Output full JSON response"),
    copy: bool = typer.Option(False, "--copy", help="Copy context to clipboard"),
):
    """Build AI-ready context from your developer memory."""
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

    intent = result.get("intent", "general")

    if as_json:
        output = {
            "query": result["query"],
            "intent": intent,
            "context_text": result["context_text"],
            "token_estimate": result["token_estimate"],
            "memory_count": result["memory_count"],
            "retrieval_trace": result.get("retrieval_trace", {}),
        }
        console.print_json(json.dumps(output))
    else:
        if format == "markdown":
            console.print(Markdown(result["context_text"]))
        else:
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

    intent_str = f" · (intent: {intent})" if intent != "general" else ""
    console.print(
        f"\n[dim]{result['memory_count']} memories · "
        f"~{result['token_estimate']} tokens{intent_str}[/dim]"
    )
