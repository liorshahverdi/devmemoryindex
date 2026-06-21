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
    no_plan: bool = typer.Option(False, "--no-plan", help="Skip query planning, search all types (original behaviour)."),
    generate: bool = typer.Option(False, "--generate", help="Use local LLM generation instead of fast extractive answering."),
):
    """Ask a question — retrieves memories and returns a cited answer."""
    if voice:
        from cli.commands._voice import transcribe_or_exit
        text = transcribe_or_exit(duration=voice_duration)
        console.print(f'\n[bold cyan]Query (voice):[/bold cyan] {text}\n')
        query = text
    elif query is None:
        console.print("[red]Provide a query or use --voice.[/red]")
        raise typer.Exit(1)
    try:
        from core.rag_engine import RAGEngine
        if not generate and not save:
            from core.backup_read_store import BackupReadStore, default_backup_path
            backup_path = default_backup_path()
            store = BackupReadStore(backup_path) if backup_path.exists() else None
        else:
            store = None
    except ImportError:
        console.print("[red]httpx is required for generated answers: uv pip install -e '.[llm]'[/red]")
        raise typer.Exit(1)

    cfg = {}
    if model:
        cfg["model"] = model

    try:
        if store is None:
            from core.store_provider import get_store
            store = get_store()
        if generate:
            from core.llm_backend import get_backend
            backend = get_backend(cfg or None)
        else:
            backend = None
        engine = RAGEngine(store, backend)
    except Exception as e:
        console.print(f"[red]Failed to initialise LLM backend: {e}[/red]")
        raise typer.Exit(1)

    if not voice:
        console.print(f"\n[bold cyan]Query:[/bold cyan] {query}\n")

    if not generate:
        answer, memories, planned = engine.ask_fast(query, repo=repo, type_filter=memory_type)
        _print_plan(planned)
        console.print(Markdown(answer))
        if speak and answer:
            from cli.commands._speak import StreamingSpeaker
            speaker = StreamingSpeaker()
            speaker.feed(answer)
            speaker.finish()
        if save and answer:
            mem_id = engine.save_answer(query, answer, repo=repo)
            if mem_id:
                console.print(f"\n[green]Answer saved as memory {mem_id[:8]}[/green]")
        return

    use_plan = not no_plan and memory_type is None

    if no_stream:
        try:
            answer, memories, planned = engine.ask(
                query, repo=repo, type_filter=memory_type, stream=False, plan=use_plan,
            )
        except Exception as e:
            console.print(f"[red]LLM error: {e}[/red]")
            _print_hint()
            raise typer.Exit(1)
        _print_plan(planned)
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
            stream_gen, planned = engine.ask(
                query, repo=repo, type_filter=memory_type, stream=True, plan=use_plan,
            )
            _print_plan(planned)
            with Live("", console=console, refresh_per_second=15) as live:
                for chunk in stream_gen:
                    chunks.append(chunk)
                    live.update("".join(chunks))
                    if speaker:
                        speaker.feed(chunk)
            if speaker:
                speaker.finish()
            answer = "".join(chunks)
        except Exception as e:
            console.print(f"\n[red]LLM error: {e}[/red]")
            _print_hint()
            raise typer.Exit(1)

    if save and answer:
        mem_id = engine.save_answer(query, answer, repo=repo)
        if mem_id:
            console.print(f"\n[green]Answer saved as memory {mem_id[:8]}[/green]")


def _print_plan(planned: dict) -> None:
    if not planned or not planned.get("type"):
        return
    t = planned.get("type", "")
    q = planned.get("query", "")
    r = planned.get("reason", "")
    console.print(f"[dim]→ searching [cyan]{t}[/cyan] for [italic]\"{q}\"[/italic]"
                  + (f"  ({r})" if r else "") + "[/dim]\n")


def _print_hint():
    console.print(
        "[yellow]Tip: make sure Ollama is running "
        "([bold]ollama serve[/bold]) and the model is pulled "
        "([bold]ollama pull mistral[/bold]).[/yellow]"
    )
