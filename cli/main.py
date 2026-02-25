import typer

app = typer.Typer(
    name="devmemory",
    help="Persistent memory for developers and AI coding agents.",
    invoke_without_command=True,
)

@app.callback()
def main():
    """Persistent memory for developers and AI coding agents."""

# Phase 1 commands (core engine only — no connectors needed)
from cli.commands.search import search
from cli.commands.add import add
from cli.commands.stats import stats

app.command()(search)
app.command()(add)
app.command()(stats)

if __name__ == "__main__":
    app()