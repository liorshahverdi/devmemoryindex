import typer
from rich.console import Console

console = Console()


def dictate(
    duration: int = typer.Option(10, "--duration", "-d", help="Recording length in seconds"),
    model: str = typer.Option("base", "--model", "-m", help="Whisper model: base, small, medium"),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Associate with a repo"),
):
    """Record your voice and auto-index it as a memory."""
    try:
        from connectors.voice_connector import VoiceConnector
    except ImportError:
        console.print(
            "[red]Audio dependencies not installed.[/red] "
            "Run: [bold]uv pip install 'devmemoryindex[voice]'[/bold]"
        )
        raise typer.Exit(1)

    console.print(f"[cyan]Recording for {duration}s... (speak now)[/cyan]")
    connector = VoiceConnector(duration=duration, model_size=model, repo=repo)
    count = connector.collect()

    if count:
        console.print("[bold green]Memory indexed.[/bold green]")
    else:
        console.print("[yellow]Nothing transcribed or already indexed.[/yellow]")
