"""
Filesystem Connector — indexes source code files from configured directories.

Files are split into 80-line chunks with a 10-line overlap so that each memory
covers a coherent block of code. IDs are content-addressed (filepath + line
range + first 200 chars of content) so unchanged chunks are silently skipped
on re-index while changed chunks are picked up as new memories.

Performance/resilience features:
  * per-file fingerprints are persisted after each successfully inspected file
    so repeated and interrupted scans skip unchanged files before embedding;
  * optional repo and max-files limits make large scans tunable;
  * `last_stats` and progress callbacks expose skipped reasons for agents.

Memory fields:
  type        "file_content"
  summary     "rel/path/to/file.py (lines N–M)"
  raw_text    chunk content (redacted)
  repo        inferred from nearest .git parent, or root directory name
  timestamp   file mtime
  importance  0.7 for entry points / main files, 0.5 for config, 0.6 default
  tags        ["code", <extension>]

Configuration:
  devmemory config add-code ~/projects/myapp
  devmemory config remove-code ~/projects/myapp
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import core.config as cfg
from connectors.base import Connector
from core.embeddings import embed
from core.schema import Memory

# Extensions to index
CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb",
    ".java", ".cpp", ".c", ".h", ".cs", ".swift", ".kt",
    ".vue", ".svelte", ".sh", ".bash", ".zsh", ".fish",
}
CONFIG_EXTENSIONS = {".toml", ".yaml", ".yml", ".env.example", ".ini", ".cfg"}

# Directories to never descend into
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "target", ".cache", "coverage",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "vendor",
    ".tox", "eggs", ".eggs", "htmlcov", "site-packages",
}

# Files to skip even if extension matches
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "poetry.lock", "uv.lock",
    "Cargo.lock", "go.sum", "go.mod",
}

MAX_FILE_BYTES = 500_000   # skip files > 500 KB (generated/minified)
CHUNK_LINES = 80
OVERLAP_LINES = 10
MIN_CHUNK_LINES = 10
MAX_CHUNK_CHARS = 3000
DEFAULT_STATE_PATH = Path.home() / ".config" / "devmemory" / "filesystem_state.json"

ProgressCallback = Callable[[dict], None]


class FilesystemIndexState:
    """Small JSON sidecar for fast unchanged-file skips."""

    def __init__(self, path: str | Path = DEFAULT_STATE_PATH):
        self.path = Path(path).expanduser()
        self.data = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
            if isinstance(data, dict) and isinstance(data.get("files"), dict):
                return data
        except Exception:
            pass
        return {"version": 1, "files": {}}

    def get(self, path: Path) -> str | None:
        return self.data["files"].get(str(path.resolve()))

    def set(self, path: Path, fingerprint: str) -> None:
        self.data["files"][str(path.resolve())] = fingerprint
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True))
        tmp.replace(self.path)


class FilesystemConnector(Connector):
    name = "filesystem"

    def __init__(
        self,
        dirs: list[str] | None = None,
        *,
        state_path: str | Path = DEFAULT_STATE_PATH,
        max_files: int | None = None,
        repo: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ):
        super().__init__()
        self.dirs = dirs or cfg.get_filesystem_dirs()
        self.state = FilesystemIndexState(state_path)
        self.max_files = max_files
        self.repo = repo
        self.progress_callback = progress_callback
        self.last_stats = self._new_stats()

    @staticmethod
    def _new_stats() -> dict:
        return {
            "roots_scanned": [],
            "inspected": 0,
            "indexed": 0,
            "chunks_added": 0,
            "skipped": Counter(),
            "errors": 0,
        }

    def _progress(self, event: str, **payload) -> None:
        if not self.progress_callback:
            return
        data = {"event": event, **payload}
        self.progress_callback(data)

    def collect(self) -> int:
        self.last_stats = self._new_stats()
        if not self.dirs:
            self._progress("summary", **self._serializable_stats())
            return 0
        count = 0
        for d in self.dirs:
            root = Path(d).expanduser().resolve()
            if not root.is_dir():
                self.last_stats["skipped"]["missing_root"] += 1
                continue
            if self.repo and root.name != self.repo and _infer_repo(root) != self.repo:
                self.last_stats["skipped"]["repo_filter"] += 1
                continue
            count += self._index_dir(root)
            if self.max_files is not None and self.last_stats["inspected"] >= self.max_files:
                break
        self._progress("summary", **self._serializable_stats())
        return count

    def _serializable_stats(self) -> dict:
        return {**self.last_stats, "skipped": dict(self.last_stats["skipped"])}

    def _candidate_paths(self, root: Path):
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            yield path

    def _index_dir(self, root: Path) -> int:
        self.last_stats["roots_scanned"].append(str(root))
        self._progress("root", root=str(root))
        count = 0
        for path in self._candidate_paths(root):
            if self.max_files is not None and self.last_stats["inspected"] >= self.max_files:
                self.last_stats["skipped"]["max_files"] += 1
                continue

            reason = _skip_reason(path)
            if reason:
                self.last_stats["skipped"][reason] += 1
                continue

            self.last_stats["inspected"] += 1
            fingerprint = _fingerprint(path)
            if self.state.get(path) == fingerprint:
                self.last_stats["skipped"]["unchanged"] += 1
                self._progress("file", path=str(path), inspected=self.last_stats["inspected"], added=0, skipped="unchanged")
                continue

            try:
                added = self._index_file(path, root)
                count += added
                self.last_stats["indexed"] += 1
                self.last_stats["chunks_added"] += added
                self.state.set(path, fingerprint)
                self._progress("file", path=str(path), inspected=self.last_stats["inspected"], added=added)
            except Exception:
                self.last_stats["errors"] += 1
                # Keep the existing best-effort behavior for scheduled daemons:
                # one bad file must not abort the entire ingest.
                self._progress("file", path=str(path), inspected=self.last_stats["inspected"], added=0, error=True)
        return count

    def _index_file(self, path: Path, root: Path) -> int:
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            return 0

        lines = text.splitlines()
        if len(lines) < MIN_CHUNK_LINES:
            self.last_stats["skipped"]["too_short"] += 1
            return 0

        repo = _infer_repo(path) or root.name
        rel_path = str(path.relative_to(root))
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        importance = _estimate_importance(path)

        # IDs already stored for this file — used to evict stale chunks below.
        existing_ids = self.store.get_ids_by_source(str(path), type_filter="file_content")
        current_ids: set[str] = set()

        added = 0
        for start, end, chunk_lines in _chunk_lines(lines):
            chunk_text = "\n".join(chunk_lines).strip()
            if not chunk_text:
                continue

            mem_id = hashlib.sha256(
                f"{path}|{start}|{chunk_text[:200]}".encode()
            ).hexdigest()

            current_ids.add(mem_id)

            if self.store.exists(mem_id):
                continue

            raw_text = self._redact(chunk_text[:MAX_CHUNK_CHARS])
            defs = _extract_definitions(chunk_text)
            def_suffix = f" · {defs}" if defs else ""
            summary = f"{rel_path} (lines {start + 1}–{end}){def_suffix}"[:200]
            embed_text = f"{rel_path} {defs}\n{chunk_text[:512]}"

            memory = Memory(
                id=mem_id,
                type="file_content",
                summary=summary,
                raw_text=raw_text,
                source=str(path),
                repo=repo,
                timestamp=mtime,
                tags=["code", path.suffix.lstrip(".") or "file"],
                importance=importance,
            )
            self.store.add(memory, embed(embed_text))
            added += 1

        # Evict chunks that were stored for this file but are no longer in the
        # current content. These accumulate silently as the file evolves and
        # pollute search results with stale code versions.
        for stale_id in existing_ids - current_ids:
            self.store.delete(stale_id)

        return added


# ── Helpers ────────────────────────────────────────────────────────────


def _skip_reason(path: Path) -> str | None:
    if any(part in SKIP_DIRS for part in path.parts):
        return "ignored_directory"
    if path.name in SKIP_FILES:
        return "ignored_file"
    ext = path.suffix.lower()
    if ext not in CODE_EXTENSIONS and ext not in CONFIG_EXTENSIONS:
        return "unsupported_extension"
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return "large_file"
    except OSError:
        return "stat_error"
    return None


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    return hashlib.sha256(f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()


def _chunk_lines(lines: list[str]) -> list[tuple[int, int, list[str]]]:
    """Yield (start_index, end_index, lines) chunks with overlap."""
    chunks = []
    total = len(lines)
    start = 0
    while start < total:
        end = min(start + CHUNK_LINES, total)
        chunk = lines[start:end]
        if len(chunk) >= MIN_CHUNK_LINES:
            chunks.append((start, end, chunk))
        if end >= total:
            break
        start = end - OVERLAP_LINES
    return chunks


def _infer_repo(path: Path) -> str | None:
    for parent in path.parents:
        if (parent / ".git").exists():
            return parent.name
    return None


def _extract_definitions(chunk_text: str) -> str:
    """Extract top-level class and function names defined in a code chunk."""
    import re
    names = []
    for line in chunk_text.splitlines():
        m = re.match(r"^(class|def|function|fn|func|type|struct|interface)\s+(\w+)", line)
        if m:
            names.append(f"{m.group(1)} {m.group(2)}")
    return ", ".join(names[:5])


def _estimate_importance(path: Path) -> float:
    name = path.stem.lower()
    # Test files are lower-priority — useful for usage examples but shouldn't
    # outrank implementation files when searching for "how does X work".
    if name.startswith("test_") or name.endswith("_test") or "tests" in path.parts:
        return 0.4
    if name in ("main", "app", "index", "server", "cli", "core", "api"):
        return 0.7
    if path.suffix.lower() in CONFIG_EXTENSIONS:
        return 0.5
    return 0.6
