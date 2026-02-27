import typer
from rich.console import Console

console = Console()


def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host"),
    port: int = typer.Option(7711, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes (dev mode)"),
):
    """Start the DevMemoryIndex REST API server."""
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[red]REST API requires api extras:[/red] "
            "uv pip install -e '.[api]'"
        )
        raise typer.Exit(1)

    console.print(f"[green]Starting DevMemoryIndex API[/green] on [bold]http://{host}:{port}[/bold]")
    console.print(f"  [dim]Docs: http://{host}:{port}/docs[/dim]")
    import uvicorn
    uvicorn.run("api.server:app", host=host, port=port, reload=reload)
