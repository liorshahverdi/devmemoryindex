import typer
from rich.console import Console
from rich.markdown import Markdown

console = Console()


def ask(
    query: str | None = typer.Argument(None, help="Question to ask your memory store."),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Filter context to a specific repo."),
    memory_type: str | None = typer.Option(None, "--type", "-t", help="Filter context to a memory type (e.g. git_diff, file_content)."),
    model: str | None = typer.Option(None, "--model", "-m", help="Override the configured LLM model."),
    no_stream: bool = typer.Option(False, "--no-stream", help="Collect full answer before printing."),
    save: bool = typer.Option(False, "--save", "-s", help="Save the answer as an agent_solution memory."),
    voice: bool = typer.Option(False, "--voice", help="Speak your question instead of typing."),
    voice_duration: int = typer.Option(5, "--voice-duration", help="Recording duration in seconds (default 5)."),
    speak: bool = typer.Option(False, "--speak", help="Read the answer aloud (British accent, synced to stream)."),
):
    """Ask a question — retrieves memories, generates a cited answer via local LLM."""
    if voice:
        from cli.commands._voice import transcribe_or_exit
        text = transcribe_or_exit(duration=voice_duration)
        console.print(f'\n[bold cyan]Query (voice):[/bold cyan] {text}\n')
        query = text
    elif query is None:
        console.print("[red]Provide a query or use --voice.[/red]")
        raise typer.Exit(1)
    try:
        from core.llm_backend import get_backend
        from core.rag_engine import RAGEngine
    except ImportError:
        console.print("[red]httpx is required: uv pip install -e '.[llm]'[/red]")
        raise typer.Exit(1)

    from core.store_provider import get_store

    cfg = {}
    if model:
        cfg["model"] = model

    try:
        backend = get_backend(cfg or None)
        store = get_store()
        engine = RAGEngine(store, backend)
    except Exception as e:
        console.print(f"[red]Failed to initialise LLM backend: {e}[/red]")
        raise typer.Exit(1)

    if not voice:
        console.print(f"\n[bold cyan]Query:[/bold cyan] {query}\n")

    if no_stream:
        try:
            answer, memories = engine.ask(query, repo=repo, type_filter=memory_type, stream=False)
        except Exception as e:
            console.print(f"[red]LLM error: {e}[/red]")
            _print_hint()
            raise typer.Exit(1)
        console.print(Markdown(answer))
        if speak:
            from cli.commands._speak import StreamingSpeaker
            speaker = StreamingSpeaker()
            speaker.feed(answer)
            speaker.finish()
    else:
        from rich.live import Live

        chunks: list[str] = []
        answer = ""
        speaker = None
        if speak:
            from cli.commands._speak import StreamingSpeaker
            speaker = StreamingSpeaker()
        try:
            with Live("", console=console, refresh_per_second=15) as live:
                for chunk in engine.ask(query, repo=repo, type_filter=memory_type, stream=True):
                    chunks.append(chunk)
                    live.update("".join(chunks))
                    if speaker:
                        speaker.feed(chunk)
            if speaker:
                speaker.finish()  # flush remainder, block until audio drains
            answer = "".join(chunks)
        except Exception as e:
            console.print(f"\n[red]LLM error: {e}[/red]")
            _print_hint()
            raise typer.Exit(1)

    if save and answer:
        mem_id = engine.save_answer(query, answer, repo=repo)
        if mem_id:
            console.print(f"\n[green]Answer saved as memory {mem_id[:8]}[/green]")


def _print_hint():
    console.print(
        "[yellow]Tip: make sure Ollama is running "
        "([bold]ollama serve[/bold]) and the model is pulled "
        "([bold]ollama pull mistral[/bold]).[/yellow]"
    )
