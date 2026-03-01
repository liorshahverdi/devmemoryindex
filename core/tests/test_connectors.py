"""Tests for filesystem and markdown connectors.

Covers pure helper functions (no I/O) directly, and tests the ingest
logic via a temp filesystem + injected MemoryStore to avoid production
state and expensive embedding calls.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from core.memory_store import MemoryStore, VECTOR_DIM


_ZERO_VEC = [0.0] * VECTOR_DIM


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "db"))


# ═══════════════════════════════════════════════════════════════════════════════
# Filesystem connector — pure helpers
# ═══════════════════════════════════════════════════════════════════════════════

from connectors.filesystem_connector import (
    _chunk_lines,
    _extract_definitions,
    _estimate_importance,
    _infer_repo,
    CHUNK_LINES,
    OVERLAP_LINES,
    MIN_CHUNK_LINES,
)


class TestChunkLines:
    def test_short_file_produces_no_chunks(self):
        lines = ["x"] * (MIN_CHUNK_LINES - 1)
        chunks = _chunk_lines(lines)
        assert chunks == []

    def test_exactly_min_lines_produces_one_chunk(self):
        lines = ["line"] * MIN_CHUNK_LINES
        chunks = _chunk_lines(lines)
        assert len(chunks) == 1
        start, end, chunk = chunks[0]
        assert start == 0
        assert end == MIN_CHUNK_LINES
        assert len(chunk) == MIN_CHUNK_LINES

    def test_large_file_produces_multiple_chunks(self):
        lines = [f"line {i}" for i in range(CHUNK_LINES * 3)]
        chunks = _chunk_lines(lines)
        assert len(chunks) > 1

    def test_chunks_overlap(self):
        """Adjacent chunks share OVERLAP_LINES lines."""
        lines = [f"L{i}" for i in range(CHUNK_LINES + OVERLAP_LINES + MIN_CHUNK_LINES)]
        chunks = _chunk_lines(lines)
        assert len(chunks) >= 2
        _, end0, _ = chunks[0]
        start1, _, _ = chunks[1]
        assert end0 - start1 == OVERLAP_LINES

    def test_last_chunk_reaches_eof(self):
        lines = [f"line {i}" for i in range(CHUNK_LINES + 20)]
        chunks = _chunk_lines(lines)
        last_end = chunks[-1][1]
        assert last_end == len(lines)


class TestExtractDefinitions:
    def test_extracts_python_class_and_def(self):
        # Only top-level (unindented) definitions are matched
        code = "class Foo:\n    pass\n\ndef bar():\n    pass"
        result = _extract_definitions(code)
        assert "class Foo" in result
        assert "def bar" in result

    def test_extracts_typescript_function(self):
        code = "function fetchData() {\n  return null;\n}"
        result = _extract_definitions(code)
        assert "function fetchData" in result

    def test_no_definitions_returns_empty(self):
        code = "x = 1\ny = 2\nprint(x + y)"
        assert _extract_definitions(code) == ""

    def test_limits_to_five_definitions(self):
        code = "\n".join(f"def func_{i}():" for i in range(10))
        result = _extract_definitions(code)
        names = result.split(", ")
        assert len(names) == 5


class TestEstimateImportance:
    def test_test_file_gets_low_importance(self, tmp_path):
        f = tmp_path / "test_foo.py"
        assert _estimate_importance(f) == pytest.approx(0.4)

    def test_main_file_gets_high_importance(self, tmp_path):
        f = tmp_path / "main.py"
        assert _estimate_importance(f) == pytest.approx(0.7)

    def test_config_file_gets_medium_importance(self, tmp_path):
        f = tmp_path / "config.toml"
        assert _estimate_importance(f) == pytest.approx(0.5)

    def test_regular_file_gets_default(self, tmp_path):
        f = tmp_path / "utils.py"
        assert _estimate_importance(f) == pytest.approx(0.6)

    def test_file_in_tests_directory_gets_low(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        f = tests_dir / "helper.py"
        assert _estimate_importance(f) == pytest.approx(0.4)


class TestFilesystemInferRepo:
    def test_finds_git_parent(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        source_file = tmp_path / "src" / "foo.py"
        source_file.parent.mkdir()
        source_file.touch()
        assert _infer_repo(source_file) == tmp_path.name

    def test_returns_none_without_git(self, tmp_path):
        f = tmp_path / "foo.py"
        f.touch()
        assert _infer_repo(f) is None


# ── FilesystemConnector integration ──────────────────────────────────────────

import connectors.base as base_mod
from connectors.filesystem_connector import FilesystemConnector


class TestFilesystemConnectorIndexFile:
    def _make_connector(self, store: MemoryStore, dirs: list[str]) -> FilesystemConnector:
        with patch.object(base_mod, "get_store", return_value=store):
            connector = FilesystemConnector(dirs=dirs)
        connector.store = store
        return connector

    def test_indexes_python_file(self, store, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        py_file = src / "main.py"
        # Write enough lines to form at least one chunk
        py_file.write_text("\n".join(
            [f"# line {i}" for i in range(MIN_CHUNK_LINES + 5)]
        ))

        connector = self._make_connector(store, [str(src)])
        with patch("connectors.filesystem_connector.embed", return_value=_ZERO_VEC):
            count = connector._index_file(py_file, src)

        assert count >= 1
        assert store.count() >= 1

    def test_skips_file_below_min_lines(self, store, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        tiny = src / "tiny.py"
        tiny.write_text("x = 1\n")

        connector = self._make_connector(store, [str(src)])
        with patch("connectors.filesystem_connector.embed", return_value=_ZERO_VEC):
            count = connector._index_file(tiny, src)

        assert count == 0

    def test_does_not_reindex_existing_chunk(self, store, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        py_file = src / "lib.py"
        py_file.write_text("\n".join([f"# line {i}" for i in range(MIN_CHUNK_LINES + 5)]))

        connector = self._make_connector(store, [str(src)])
        with patch("connectors.filesystem_connector.embed", return_value=_ZERO_VEC):
            first = connector._index_file(py_file, src)
            second = connector._index_file(py_file, src)

        assert first >= 1
        assert second == 0   # already indexed

    def test_collects_from_directory(self, store, tmp_path):
        src = tmp_path / "project"
        src.mkdir()
        (src / "a.py").write_text("\n".join([f"# line {i}" for i in range(MIN_CHUNK_LINES + 5)]))
        (src / "b.py").write_text("\n".join([f"# line {i}" for i in range(MIN_CHUNK_LINES + 5)]))

        connector = self._make_connector(store, [str(src)])
        with patch("connectors.filesystem_connector.embed", return_value=_ZERO_VEC):
            count = connector.collect()

        assert count >= 2

    def test_stale_chunks_evicted_on_reindex(self, store, tmp_path):
        """When file content changes, old chunks are deleted on the next index run."""
        src = tmp_path / "src"
        src.mkdir()
        py_file = src / "lib.py"

        # First version: write enough lines for exactly one chunk
        v1_lines = [f"# version 1 line {i}" for i in range(MIN_CHUNK_LINES + 2)]
        py_file.write_text("\n".join(v1_lines))

        connector = self._make_connector(store, [str(src)])
        with patch("connectors.filesystem_connector.embed", return_value=_ZERO_VEC):
            added_v1 = connector._index_file(py_file, src)

        assert added_v1 >= 1
        count_after_v1 = store.count()

        # Second version: completely different content — all chunk IDs change
        v2_lines = [f"# version 2 totally different {i}" for i in range(MIN_CHUNK_LINES + 2)]
        py_file.write_text("\n".join(v2_lines))

        with patch("connectors.filesystem_connector.embed", return_value=_ZERO_VEC):
            added_v2 = connector._index_file(py_file, src)

        # New chunks were added for v2 content
        assert added_v2 >= 1
        # Store count should be the same as after v1 (stale v1 chunks evicted,
        # replaced by same number of v2 chunks)
        assert store.count() == count_after_v1

        # All remaining memories should reflect v2 content
        rows = store.get_all()
        for row in rows:
            assert "version 2" in row["raw_text"]

    def test_unchanged_file_evicts_nothing(self, store, tmp_path):
        """Re-indexing an unchanged file adds 0 and evicts 0."""
        src = tmp_path / "src"
        src.mkdir()
        py_file = src / "stable.py"
        py_file.write_text("\n".join([f"# stable line {i}" for i in range(MIN_CHUNK_LINES + 5)]))

        connector = self._make_connector(store, [str(src)])
        with patch("connectors.filesystem_connector.embed", return_value=_ZERO_VEC):
            connector._index_file(py_file, src)
            count_before = store.count()
            added = connector._index_file(py_file, src)

        assert added == 0
        assert store.count() == count_before  # nothing evicted either

    def test_get_ids_by_source(self, store, tmp_path):
        """MemoryStore.get_ids_by_source returns IDs for the given source path."""
        src = tmp_path / "src"
        src.mkdir()
        py_file = src / "module.py"
        py_file.write_text("\n".join([f"# line {i}" for i in range(MIN_CHUNK_LINES + 5)]))

        connector = self._make_connector(store, [str(src)])
        with patch("connectors.filesystem_connector.embed", return_value=_ZERO_VEC):
            connector._index_file(py_file, src)

        ids = store.get_ids_by_source(str(py_file), type_filter="file_content")
        assert len(ids) >= 1
        # All returned IDs should actually exist in the store
        for mem_id in ids:
            assert store.exists(mem_id)

    def test_get_ids_by_source_empty_for_unknown_path(self, store):
        ids = store.get_ids_by_source("/no/such/file.py", type_filter="file_content")
        assert ids == set()


# ═══════════════════════════════════════════════════════════════════════════════
# Markdown connector — pure helpers
# ═══════════════════════════════════════════════════════════════════════════════

from connectors.markdown_connector import (
    _parse_frontmatter,
    _chunk_by_h2,
    _infer_repo as md_infer_repo,
)


class TestParseFrontmatter:
    def test_no_frontmatter(self):
        text = "# Hello\nSome content here."
        fm, body = _parse_frontmatter(text)
        assert fm == {}
        assert "Hello" in body

    def test_parses_simple_frontmatter(self):
        text = "---\ntitle: My Note\ntags: python, dev\n---\nBody text."
        fm, body = _parse_frontmatter(text)
        assert fm["title"] == "My Note"
        assert "Body text" in body

    def test_parses_yaml_list_tags(self):
        text = "---\ntags: [foo, bar, baz]\n---\nContent."
        fm, body = _parse_frontmatter(text)
        assert fm["tags"] == ["foo", "bar", "baz"]

    def test_unclosed_frontmatter_treated_as_no_frontmatter(self):
        text = "---\ntitle: broken\nno closing fence"
        fm, body = _parse_frontmatter(text)
        assert fm == {}

    def test_empty_frontmatter(self):
        text = "---\n---\nJust body."
        fm, body = _parse_frontmatter(text)
        assert fm == {}
        assert "Just body" in body


class TestChunkByH2:
    def test_no_headings_produces_single_chunk(self):
        body = "Some introductory text that is long enough."
        chunks = _chunk_by_h2(body, "My File")
        assert len(chunks) == 1
        assert chunks[0][0] == "My File"

    def test_splits_at_h2_headings(self):
        body = "Intro text.\n## Section One\nContent one.\n## Section Two\nContent two."
        chunks = _chunk_by_h2(body, "Doc")
        titles = [c[0] for c in chunks]
        assert "Doc" in titles
        assert "Doc > Section One" in titles
        assert "Doc > Section Two" in titles

    def test_h3_not_split(self):
        body = "Intro.\n### Sub heading\nMore content."
        chunks = _chunk_by_h2(body, "File")
        # ### should not trigger a new chunk — whole body is one intro chunk
        assert len(chunks) == 1

    def test_empty_section_excluded(self):
        body = "## Heading One\n\n## Heading Two\nActual content here."
        chunks = _chunk_by_h2(body, "File")
        titles = [c[0] for c in chunks]
        assert "File > Heading One" not in titles
        assert "File > Heading Two" in titles


class TestMarkdownInferRepo:
    def test_finds_git_parent(self, tmp_path):
        (tmp_path / ".git").mkdir()
        md = tmp_path / "notes" / "foo.md"
        md.parent.mkdir()
        md.touch()
        assert md_infer_repo(md) == tmp_path.name

    def test_returns_none_without_git(self, tmp_path):
        md = tmp_path / "foo.md"
        md.touch()
        assert md_infer_repo(md) is None


# ── MarkdownConnector integration ─────────────────────────────────────────────

from connectors.markdown_connector import MarkdownConnector


class TestMarkdownConnectorIngestFile:
    def _make_connector(self, store: MemoryStore) -> MarkdownConnector:
        with patch.object(base_mod, "get_store", return_value=store):
            connector = MarkdownConnector()
        connector.store = store
        return connector

    def test_ingests_simple_markdown(self, store, tmp_path):
        md = tmp_path / "note.md"
        # Body must exceed MIN_CHUNK_LEN (80 chars)
        md.write_text("# My Note\n\n" + "This is some meaningful content. " * 5)

        connector = self._make_connector(store)
        with patch("connectors.markdown_connector.embed", return_value=_ZERO_VEC):
            count = connector._ingest_file(md)

        assert count >= 1
        assert store.count() >= 1

    def test_ingests_sections_separately(self, store, tmp_path):
        md = tmp_path / "guide.md"
        section_body = "Detailed explanation here. " * 5
        md.write_text(
            f"Intro paragraph. " * 6 + "\n\n"
            f"## Section Alpha\n{section_body}\n\n"
            f"## Section Beta\n{section_body}"
        )

        connector = self._make_connector(store)
        with patch("connectors.markdown_connector.embed", return_value=_ZERO_VEC):
            count = connector._ingest_file(md)

        assert count == 3   # intro + 2 sections

    def test_important_tag_raises_importance(self, store, tmp_path):
        md = tmp_path / "critical.md"
        md.write_text("---\ntags: [important]\n---\n" + "Critical information. " * 10)

        connector = self._make_connector(store)
        with patch("connectors.markdown_connector.embed", return_value=_ZERO_VEC):
            connector._ingest_file(md)

        rows = store.get_all()
        assert rows[0]["importance"] == pytest.approx(0.85)

    def test_skips_short_chunks(self, store, tmp_path):
        md = tmp_path / "stub.md"
        md.write_text("## Section\nToo short.")  # < 80 chars

        connector = self._make_connector(store)
        with patch("connectors.markdown_connector.embed", return_value=_ZERO_VEC):
            count = connector._ingest_file(md)

        assert count == 0

    def test_does_not_reindex_unchanged_file(self, store, tmp_path):
        md = tmp_path / "stable.md"
        md.write_text("# Stable\n\n" + "Content that does not change. " * 5)

        connector = self._make_connector(store)
        with patch("connectors.markdown_connector.embed", return_value=_ZERO_VEC):
            first = connector._ingest_file(md)
            second = connector._ingest_file(md)

        assert first >= 1
        assert second == 0

    def test_frontmatter_tags_propagated(self, store, tmp_path):
        md = tmp_path / "tagged.md"
        md.write_text("---\ntags: [python, backend]\n---\n" + "Technical content. " * 10)

        connector = self._make_connector(store)
        with patch("connectors.markdown_connector.embed", return_value=_ZERO_VEC):
            connector._ingest_file(md)

        rows = store.get_all()
        assert "python" in rows[0]["tags"]
        assert "backend" in rows[0]["tags"]
        assert "markdown" in rows[0]["tags"]
