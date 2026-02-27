"""
Tests for GitConnector:
1. 3 commits in a temp repo → 3 memories stored.
2. Running collect() twice produces no duplicates (second run returns 0).
3. Bug-fix commit messages get importance 0.9.
"""

import subprocess
import pytest
from unittest.mock import patch

from connectors.git_connector import GitConnector
from core.memory_store import MemoryStore


def _make_git_repo(path) -> str:
    """Create a minimal git repo with 3 commits. Returns repo path as str."""
    repo = str(path)
    subprocess.run(["git", "init", repo], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "test@test.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "Test"],
                   check=True, capture_output=True)

    commits = [
        ("docs: update README with setup instructions", "README.md"),
        ("feat: add user authentication module", "auth.py"),
        ("fix: resolve bug in payment processing", "payment.py"),
    ]
    for msg, filename in commits:
        filepath = path / filename
        filepath.write_text(f"# {filename}\n")
        subprocess.run(["git", "-C", repo, "add", filename],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", repo, "commit", "-m", msg],
                       check=True, capture_output=True)

    return repo


@pytest.fixture
def git_repo(tmp_path):
    return _make_git_repo(tmp_path / "repo")


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "db"))


def _make_connector(repo_path: str, store: MemoryStore) -> GitConnector:
    """Build a GitConnector wired to a specific isolated store."""
    connector = GitConnector.__new__(GitConnector)
    connector.store = store
    connector.repo_paths = [repo_path]
    return connector


# ── Tests ─────────────────────────────────────────────────────────────


def test_collect_indexes_all_commits(git_repo, store, tmp_path):
    """3 commits in the temp repo → 3 memories in the store."""
    connector = _make_connector(git_repo, store)
    count = connector.collect()

    assert count == 3, f"Expected 3 new memories, got {count}"
    assert store.count() == 3


def test_collect_deduplicates_on_second_run(git_repo, store, tmp_path):
    """Running collect() twice must not create duplicate memories."""
    connector = _make_connector(git_repo, store)
    first_run = connector.collect()
    second_run = connector.collect()

    assert first_run == 3
    assert second_run == 0, "Second run should skip all already-indexed commits"
    assert store.count() == 3


def test_bugfix_commit_gets_high_importance(git_repo, store, tmp_path):
    """A commit message containing 'fix' or 'bug' must get importance 0.9."""
    connector = _make_connector(git_repo, store)
    connector.collect()

    rows = store.get_all()
    fix_rows = [r for r in rows if "fix" in r["summary"].lower() or "bug" in r["summary"].lower()]

    assert len(fix_rows) >= 1, "Expected at least one fix/bug commit"
    for r in fix_rows:
        assert r["importance"] == pytest.approx(0.9), (
            f"Fix commit {r['summary']!r} should have importance 0.9, got {r['importance']}"
        )
