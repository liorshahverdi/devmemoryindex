"""
devmemory api-key — manage the REST API authentication key.

Commands:
  generate  — create a new 64-char hex key and save to config
  show      — print the currently configured key
  revoke    — remove the key (re-opens the server to unauthenticated access)
"""

import secrets

import typer
from rich.console import Console

import core.config as cfg

app = typer.Typer(help="Manage the REST API authentication key.")
console = Console()


@app.command()
def generate():
    """Generate a new API key and save it to config."""
    key = secrets.token_hex(32)  # 64 hex chars
    cfg.set_api_key(key)
    console.print("[green]API key saved.[/green]")
    console.print(f"Use: [bold]Authorization: Bearer {key}[/bold]")


@app.command()
def show():
    """Print the currently configured API key."""
    key = cfg.get_api_key()
    if key is None:
        console.print("[yellow]No API key configured.[/yellow] Run [bold]devmemory api-key generate[/bold] to create one.")
    else:
        console.print(f"Current key: [bold]{key}[/bold]")


@app.command()
def revoke():
    """Remove the API key (server returns to open/unauthenticated access)."""
    if cfg.get_api_key() is None:
        console.print("[yellow]No API key configured — nothing to revoke.[/yellow]")
        return
    cfg.delete_api_key()
    console.print("[green]API key revoked.[/green] Server will accept all requests.")
