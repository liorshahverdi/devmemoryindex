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

# Phase 3.A — context command
from cli.commands.context import context
app.command()(context)

# Phase 3.B — suggest command
from cli.commands.suggest import suggest
app.command()(suggest)

# Phase 5.4B — memory pruning
from cli.commands.prune import prune
app.command()(prune)

# Phase 2 — connector ingestion
from cli.commands.ingest import ingest
app.command()(ingest)

# Phase 2.9 — voice dictation
from cli.commands.dictate import dictate
app.command()(dictate)

# Config management (devmemory config add/remove/list/scan)
from cli.commands.config_cmd import app as config_app
app.add_typer(config_app, name="config")

# Phase 2.9b — voice enroll (devmemory voice enroll)
from cli.commands.enroll import enroll
voice_app = typer.Typer(help="Voice commands (enrollment, speaker profile).")
voice_app.command("enroll")(enroll)
app.add_typer(voice_app, name="voice")

# Phase 3.D — daemon, export/import, repl
from cli.commands.daemon_cmd import app as daemon_app
from cli.commands.export import export, import_memories
from cli.commands.repl import repl

app.add_typer(daemon_app, name="daemon")
app.command(name="export")(export)
app.command(name="import")(import_memories)
app.command()(repl)

# Phase 4B — REST API server
from cli.commands.serve import serve
app.command()(serve)

# Phase 4B.2 — API key management
from cli.commands.api_key_cmd import app as api_key_app
app.add_typer(api_key_app, name="api-key")

# Daemon log viewer
from cli.commands.log_cmd import log
app.command()(log)

# Memory inspector
from cli.commands.get_cmd import get
app.command()(get)

if __name__ == "__main__":
    app()