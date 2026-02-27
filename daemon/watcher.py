"""
Filesystem watcher for DevMemoryIndex.

Watches configured markdown scan dirs for .md file changes and triggers
MarkdownConnector immediately rather than waiting for the next poll cycle.
Uses a 2-second debounce window so rapid saves don't cause repeated ingests.

Usage: started automatically by the daemon scheduler as a background thread.
Requires: watchdog  (uv pip install "devmemoryindex[watch]")
"""

import threading
import time
from pathlib import Path

import daemon.daemon_log as dlog

_DEBOUNCE = 2.0  # seconds between last event and actual ingest


class _MarkdownHandler:
    """Accumulates changed .md paths with debounce."""

    def __init__(self):
        self._pending: dict[str, float] = {}  # path → last-event timestamp
        self._lock = threading.Lock()

    def on_event(self, path: str) -> None:
        if path.endswith(".md"):
            with self._lock:
                self._pending[path] = time.time()

    def flush_due(self) -> list[str]:
        """Return and remove paths whose debounce window has elapsed."""
        now = time.time()
        with self._lock:
            due = [p for p, t in self._pending.items() if now - t >= _DEBOUNCE]
            for p in due:
                del self._pending[p]
        return due


def _make_watchdog_handler(md_handler: _MarkdownHandler):
    from watchdog.events import FileSystemEventHandler

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if not event.is_directory:
                md_handler.on_event(event.src_path)

        def on_created(self, event):
            if not event.is_directory:
                md_handler.on_event(event.src_path)

        def on_moved(self, event):
            if not event.is_directory:
                md_handler.on_event(event.dest_path)

    return _Handler()


def _run() -> None:
    try:
        from watchdog.observers import Observer
    except ImportError:
        dlog.write("Watcher: watchdog not installed — file watching disabled", level="WARN")
        return

    from core.config import get_markdown_dirs

    dirs = get_markdown_dirs()
    if not dirs:
        dlog.write("Watcher: no markdown dirs configured — watcher idle")
        return

    md_handler = _MarkdownHandler()
    wd_handler = _make_watchdog_handler(md_handler)
    observer = Observer()

    for d in dirs:
        if Path(d).is_dir():
            observer.schedule(wd_handler, d, recursive=True)
            dlog.write(f"Watcher: watching {d}")
        else:
            dlog.write(f"Watcher: skipping missing dir {d}", level="WARN")

    observer.start()
    dlog.write("Watcher: started")

    try:
        while observer.is_alive():
            time.sleep(1)
            due = md_handler.flush_due()
            if not due:
                continue
            dlog.write(f"Watcher: {len(due)} file(s) changed, re-indexing markdown")
            try:
                from connectors.markdown_connector import MarkdownConnector
                count = MarkdownConnector().collect()
                if count > 0:
                    dlog.write(f"Watcher: +{count} new memories from file changes")
            except Exception as e:
                dlog.write(f"Watcher: ingest error: {e}", level="ERROR")
    finally:
        observer.stop()
        observer.join()
        dlog.write("Watcher: stopped")


def start_watcher() -> threading.Thread:
    """Start the filesystem watcher in a daemon thread. Returns the thread."""
    t = threading.Thread(target=_run, daemon=True, name="devmemory-watcher")
    t.start()
    return t
