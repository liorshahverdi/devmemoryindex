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

# Phase 5.4B — memory pruning
from cli.commands.prune import prune
app.command()(prune)

# Phase 2.9 — voice dictation
from cli.commands.dictate import dictate
app.command()(dictate)

# Phase 2.9b — voice enroll (devmemory voice enroll)
from cli.commands.enroll import enroll
voice_app = typer.Typer(help="Voice commands (enrollment, speaker profile).")
voice_app.command("enroll")(enroll)
app.add_typer(voice_app, name="voice")

if __name__ == "__main__":
    app()