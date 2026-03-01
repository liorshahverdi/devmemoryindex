"""
devmemory plan — generate a grounded implementation plan from memory + git context.

Phase 7.9
"""

import typer
from rich.console import Console
from rich.markdown import Markdown

console = Console()


def plan(
    description: str = typer.Argument(..., help="Task description in plain language"),
    repo: str = typer.Option(None, "--repo", "-r", help="Filter memories to this repo"),
    file: list[str] = typer.Option([], "--file", "-f", help="Files you're editing (repeatable)"),
    save: bool = typer.Option(False, "--save", "-s", help="Save the plan as an agent_solution memory"),
):
    """Generate a numbered step-by-step implementation plan backed by memory + git state."""
    from core.store_provider import get_store
    from core.context_engine import ContextEngine
    from core.plan_engine import plan_task, get_git_context
    from mcp_server.tools import _file_signals

    store = get_store()
    engine = ContextEngine(store)

    # Enrich query with file signals if provided
    file_signals = _file_signals(file) if file else ""
    enriched_query = f"{description} {file_signals}".strip()

    context_result = engine.build(query=enriched_query, repo=repo, max_tokens=2000, format="raw")
    memory_context = context_result["context_text"]
    memory_count = context_result.get("memory_count", 0)

    git_context = get_git_context()

    console.print(f"[dim]Using {memory_count} memories. Generating plan via LLM...[/dim]")
    try:
        plan_text = plan_task(description, memory_context, git_context, file or None)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print()
    console.print(Markdown(plan_text))

    if save:
        from mcp_server.tools import remember_memory
        result = remember_memory(
            summary=f"Plan: {description[:160]}",
            raw_text=plan_text,
            memory_type="agent_solution",
            repo=repo,
            importance=0.8,
            tags=["plan", "generated"],
        )
        console.print(f"\n[green]Saved plan as memory {result['id'][:8]}[/green]")
