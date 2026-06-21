import threading
import time
from datetime import date
from rich.console import Console
from connectors.registry import get_connectors
from core.config import get_connector_interval
from daemon.jobs.memory_cleanup import prune_memories
from daemon.jobs.dedup import dedup_memories
from daemon.jobs.edge_inference import run_edge_inference
from daemon.watcher import start_watcher
import daemon.daemon_log as dlog

console = Console()

# Poll frequency: how often the loop wakes up to check connector due-times.
_POLL_INTERVAL = 60  # seconds


def _log(message: str, level: str = "INFO") -> None:
    """Write to log file and echo to terminal."""
    dlog.write(message, level)
    if level == "ERROR":
        console.print(f"[red]{message}[/red]")
    elif level == "WARN":
        console.print(f"[yellow]{message}[/yellow]")
    else:
        console.print(message)


def run_daemon(jarvis: bool = False):
    """Run connectors on independent per-connector schedules.

    Each connector fires when `now - last_run >= configured_interval`.
    The loop wakes every 60 s to check — so the real granularity is ±60 s.
    Logs are written to ~/.local/share/devmemory/daemon.log and trimmed daily.

    Args:
        jarvis: When True, start the wake word listener thread alongside the
                connector loop. Requires devmemory[jarvis] to be installed.
    """
    connectors = get_connectors()

    # Trim on startup to handle any log growth since last run
    removed = dlog.trim()
    if removed:
        console.print(f"[dim]Log trimmed: removed {removed} old lines[/dim]")

    _log("DevMemoryIndex daemon started")
    for c in connectors:
        interval = get_connector_interval(c.name)
        _log(f"  [{c.name}] every {_fmt_interval(interval)}")

    # Start filesystem watcher in background thread
    start_watcher()

    # Start wake word listener + voice pipeline if --jarvis mode is enabled
    if jarvis:
        try:
            from daemon.wake_word import start_wake_word_thread
            from daemon.voice_pipeline import VoicePipeline
            start_wake_word_thread()
            _log("Wake word listener started — say 'hey jarvis' to activate")
            threading.Thread(
                target=VoicePipeline().run,
                daemon=True,
                name="devmemory-pipeline",
            ).start()
            _log("Voice pipeline active — say 'hey jarvis' to start")
        except Exception as exc:
            _log(f"Jarvis mode failed to start: {exc}", "WARN")

    last_run: dict[str, float] = {}  # connector name → last run timestamp
    periodic_state: dict[str, date | None] = {}

    while True:
        now = time.time()

        for c in connectors:
            interval = get_connector_interval(c.name)
            if now - last_run.get(c.name, 0) < interval:
                continue
            try:
                count = c.collect()
                if count > 0:
                    _log(f"[{c.name}] +{count} memories")
            except Exception as e:
                _log(f"[{c.name}] Error: {e}", level="ERROR")
            last_run[c.name] = time.time()

        _run_periodic_jobs(date.today(), periodic_state)

        time.sleep(_POLL_INTERVAL)


def _run_periodic_jobs(today: date, state: dict[str, date | None]) -> None:
    """Run date-based daemon maintenance jobs once per configured period.

    Kept separate from the infinite connector loop so scheduling behavior can be
    regression-tested without sleeping or starting long-lived watchers.
    """
    if state.get("last_prune_date") != today:
        pruned = prune_memories()
        if pruned > 0:
            _log(f"Pruned {pruned} underutilized memories")
        state["last_prune_date"] = today

    # Dedup once per week (Monday)
    if today.weekday() == 0 and state.get("last_dedup_date") != today:
        removed = dedup_memories()
        if removed > 0:
            _log(f"Dedup removed {removed} duplicate memories")
        state["last_dedup_date"] = today

    # Infer memory graph edges once per week (Monday), after ingestion has had
    # time to accumulate commits, failure notes, and agent solutions.
    if today.weekday() == 0 and state.get("last_edge_inference_date") != today:
        try:
            result = run_edge_inference()
            edges_added = result.get("edges_added", 0)
            pairs_scanned = result.get("pairs_scanned", 0)
            if edges_added > 0:
                _log(
                    f"Auto-linked {edges_added} memory graph edges "
                    f"({pairs_scanned} pairs scanned)"
                )
        except Exception as exc:
            _log(f"Edge inference failed: {exc}", level="WARN")
        state["last_edge_inference_date"] = today

    # Trim log once per day
    if state.get("last_trim_date") != today:
        removed = dlog.trim()
        if removed:
            _log(f"Log trimmed: removed {removed} old lines")
        state["last_trim_date"] = today


def _fmt_interval(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m" if m else f"{h}h"
