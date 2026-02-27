"""
Tests for FilesystemConnector:
1. Basic indexing — source files chunked and stored as memories.
2. Deduplication — second collect() on unchanged files returns 0.
3. SKIP_DIRS respected — files inside node_modules/.git/etc. are not indexed.
4. File too small (< MIN_CHUNK_LINES) is skipped.
5. Unsupported extension is skipped.
6. _chunk_lines produces correct overlap.
7. _estimate_importance returns correct values.
"""

import pytest
from connectors.filesystem_connector import (
    FilesystemConnector,
    _chunk_lines,
    _estimate_importance,
    MIN_CHUNK_LINES,
    CHUNK_LINES,
    OVERLAP_LINES,
)
from core.memory_store import MemoryStore
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "db"))


@pytest.fixture
def code_dir(tmp_path):
    d = tmp_path / "project"
    d.mkdir()
    return d


def _connector(store, dirs):
    c = FilesystemConnector(dirs=[str(d) for d in dirs])
    c.store = store
    return c


def _write_py(path: Path, n_lines: int) -> Path:
    path.write_text("\n".join(f"x = {i}" for i in range(n_lines)))
    return path


# ── Basic indexing ─────────────────────────────────────────────────────────────

def test_basic_indexing(store, code_dir):
    _write_py(code_dir / "main.py", 100)
    c = _connector(store, [code_dir])
    count = c.collect()
    assert count >= 1
    memories = store.get_all()
    assert any(m["type"] == "file_content" for m in memories)


def test_summary_contains_filename(store, code_dir):
    _write_py(code_dir / "utils.py", 100)
    c = _connector(store, [code_dir])
    c.collect()
    memories = store.get_all()
    assert any("utils.py" in m["summary"] for m in memories)


# ── Deduplication ──────────────────────────────────────────────────────────────

def test_deduplication(store, code_dir):
    _write_py(code_dir / "app.py", 100)
    c = _connector(store, [code_dir])
    first = c.collect()
    second = c.collect()
    assert first >= 1
    assert second == 0  # unchanged — already indexed


# ── SKIP_DIRS ─────────────────────────────────────────────────────────────────

def test_skip_dirs_not_indexed(store, code_dir):
    skip = code_dir / "node_modules"
    skip.mkdir()
    _write_py(skip / "index.js", 100)
    c = _connector(store, [code_dir])
    assert c.collect() == 0


def test_git_dir_not_indexed(store, code_dir):
    git = code_dir / ".git"
    git.mkdir()
    (git / "config").write_text("\n".join(f"[core]" for _ in range(20)))
    c = _connector(store, [code_dir])
    assert c.collect() == 0


# ── File too small ─────────────────────────────────────────────────────────────

def test_small_file_skipped(store, code_dir):
    _write_py(code_dir / "tiny.py", MIN_CHUNK_LINES - 1)
    c = _connector(store, [code_dir])
    assert c.collect() == 0


# ── Unsupported extension ──────────────────────────────────────────────────────

def test_unsupported_extension_skipped(store, code_dir):
    (code_dir / "data.csv").write_text("\n".join(f"a,b,{i}" for i in range(100)))
    c = _connector(store, [code_dir])
    assert c.collect() == 0


# ── _chunk_lines ──────────────────────────────────────────────────────────────

def test_chunk_lines_single_chunk():
    lines = [f"line {i}" for i in range(CHUNK_LINES)]
    chunks = _chunk_lines(lines)
    assert len(chunks) == 1
    start, end, chunk = chunks[0]
    assert start == 0
    assert end == CHUNK_LINES
    assert len(chunk) == CHUNK_LINES


def test_chunk_lines_overlap():
    total = CHUNK_LINES + 20
    lines = [f"line {i}" for i in range(total)]
    chunks = _chunk_lines(lines)
    assert len(chunks) == 2
    # Second chunk starts with overlap from first
    _, end1, _ = chunks[0]
    start2, _, _ = chunks[1]
    assert start2 == end1 - OVERLAP_LINES


def test_chunk_lines_no_tiny_final_chunk():
    """A file that is just barely bigger than CHUNK_LINES won't produce
    a tiny trailing chunk smaller than MIN_CHUNK_LINES."""
    lines = [f"line {i}" for i in range(CHUNK_LINES + 5)]
    chunks = _chunk_lines(lines)
    for _, _, chunk in chunks:
        assert len(chunk) >= MIN_CHUNK_LINES


# ── _estimate_importance ──────────────────────────────────────────────────────

def test_importance_main_file(tmp_path):
    assert _estimate_importance(tmp_path / "main.py") == 0.7


def test_importance_index_file(tmp_path):
    assert _estimate_importance(tmp_path / "index.ts") == 0.7


def test_importance_config_file(tmp_path):
    assert _estimate_importance(tmp_path / "settings.toml") == 0.5


def test_importance_default(tmp_path):
    assert _estimate_importance(tmp_path / "helpers.py") == 0.6
