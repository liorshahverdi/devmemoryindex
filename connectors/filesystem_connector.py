"""
Filesystem Connector — indexes source code files from configured directories.

Files are split into 80-line chunks with a 10-line overlap so that each memory
covers a coherent block of code. IDs are content-addressed (filepath + line
range + first 200 chars of content) so unchanged chunks are silently skipped
on re-index while changed chunks are picked up as new memories.

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

import hashlib
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


class FilesystemConnector(Connector):
    name = "filesystem"

    def __init__(self, dirs: list[str] | None = None):
        super().__init__()
        self.dirs = dirs or cfg.get_filesystem_dirs()

    def collect(self) -> int:
        if not self.dirs:
            return 0
        count = 0
        for d in self.dirs:
            root = Path(d).expanduser().resolve()
            if not root.is_dir():
                continue
            count += self._index_dir(root)
        return count

    def _index_dir(self, root: Path) -> int:
        count = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            # Skip files inside ignored directories
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.name in SKIP_FILES:
                continue
            ext = path.suffix.lower()
            if ext not in CODE_EXTENSIONS and ext not in CONFIG_EXTENSIONS:
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            try:
                count += self._index_file(path, root)
            except Exception:
                pass
        return count

    def _index_file(self, path: Path, root: Path) -> int:
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            return 0

        lines = text.splitlines()
        if len(lines) < MIN_CHUNK_LINES:
            return 0

        repo = _infer_repo(path) or root.name
        rel_path = str(path.relative_to(root))
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        importance = _estimate_importance(path)

        added = 0
        for start, end, chunk_lines in _chunk_lines(lines):
            chunk_text = "\n".join(chunk_lines).strip()
            if not chunk_text:
                continue

            mem_id = hashlib.sha256(
                f"{path}|{start}|{chunk_text[:200]}".encode()
            ).hexdigest()

            if self.store.exists(mem_id):
                continue

            raw_text = self._redact(chunk_text[:MAX_CHUNK_CHARS])
            summary = f"{rel_path} (lines {start + 1}–{end})"[:200]
            embed_text = f"{rel_path}\n{chunk_text[:512]}"

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
        return added


# ── Helpers ────────────────────────────────────────────────────────────


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


def _estimate_importance(path: Path) -> float:
    name = path.stem.lower()
    if name in ("main", "app", "index", "server", "cli", "core", "api"):
        return 0.7
    if path.suffix.lower() in CONFIG_EXTENSIONS:
        return 0.5
    return 0.6
