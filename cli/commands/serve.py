import typer
from rich.console import Console

console = Console()


def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host"),
    port: int = typer.Option(7711, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes (dev mode)"),
    no_auth: bool = typer.Option(False, "--no-auth", help="Disable API key enforcement (even if a key is configured)"),
):
    """Start the DevMemoryIndex REST API server."""
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        console.print(
            "[red]REST API requires api extras:[/red] "
            "uv pip install -e '.[api]'"
        )
        raise typer.Exit(1)

    from api.server import start_server
    import core.config as cfg

    key = cfg.get_api_key()
    if no_auth:
        console.print(f"[green]Starting DevMemoryIndex API[/green] on [bold]http://{host}:{port}[/bold] [yellow](auth disabled)[/yellow]")
    elif key:
        console.print(f"[green]Starting DevMemoryIndex API[/green] on [bold]http://{host}:{port}[/bold] [green](auth enabled)[/green]")
    else:
        console.print(f"[green]Starting DevMemoryIndex API[/green] on [bold]http://{host}:{port}[/bold] [dim](no auth — run 'devmemory api-key generate' to enable)[/dim]")
    console.print(f"  [dim]Docs: http://{host}:{port}/docs[/dim]")

    start_server(host=host, port=port, reload=reload, auth_enabled=not no_auth)
