"""
Daemon file logger.

Writes timestamped lines to ~/.local/share/devmemory/daemon.log.
Trims the file to MAX_LINES on startup and once per day to prevent unbounded growth.
"""

from datetime import datetime
from pathlib import Path

LOG_PATH = Path.home() / ".local" / "share" / "devmemory" / "daemon.log"
MAX_LINES = 5_000  # lines kept after each trim


def _ensure() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def write(message: str, level: str = "INFO") -> None:
    """Append a single timestamped line to the log file."""
    _ensure()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{ts} [{level}] {message}\n")


def trim(max_lines: int = MAX_LINES) -> int:
    """Trim the log file to the most recent max_lines lines.

    Returns the number of lines removed.
    """
    if not LOG_PATH.exists():
        return 0
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    if len(lines) <= max_lines:
        return 0
    removed = len(lines) - max_lines
    LOG_PATH.write_text("".join(lines[-max_lines:]), encoding="utf-8")
    return removed


def tail(n: int = 50) -> list[str]:
    """Return the last n lines of the log (no trailing newline)."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    return lines[-n:]
