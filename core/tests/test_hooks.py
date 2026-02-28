"""
Tests for core/hooks.py — git post-commit hook management.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

from core.hooks import (
    HOOK_MARKER_START,
    HOOK_MARKER_END,
    install_hook,
    uninstall_hook,
    hook_status,
    _strip_hook_block,
)


@pytest.fixture
def git_repo(tmp_path):
    """Minimal git repo initialised in a temp directory."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    return str(tmp_path)


@pytest.fixture
def non_repo(tmp_path):
    """Plain directory with no .git subdirectory."""
    return str(tmp_path)


# ── install_hook ──────────────────────────────────────────────────────────────


def test_install_creates_hook_file(git_repo):
    result = install_hook(git_repo)
    assert result == "installed"
    hook = Path(git_repo) / ".git" / "hooks" / "post-commit"
    assert hook.exists()


def test_install_hook_contains_marker_and_command(git_repo):
    install_hook(git_repo)
    content = (Path(git_repo) / ".git" / "hooks" / "post-commit").read_text()
    assert HOOK_MARKER_START in content
    assert HOOK_MARKER_END in content
    assert "devmemory ingest --source git" in content


def test_install_hook_is_executable(git_repo):
    install_hook(git_repo)
    hook = Path(git_repo) / ".git" / "hooks" / "post-commit"
    assert hook.stat().st_mode & stat.S_IXUSR


def test_install_returns_already_installed_on_second_call(git_repo):
    install_hook(git_repo)
    result = install_hook(git_repo)
    assert result == "already_installed"


def test_install_appends_to_existing_hook(git_repo):
    hook = Path(git_repo) / ".git" / "hooks" / "post-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho 'existing hook'\n")
    result = install_hook(git_repo)
    assert result == "appended"
    content = hook.read_text()
    assert "existing hook" in content
    assert HOOK_MARKER_START in content


def test_install_non_repo_returns_error(non_repo):
    result = install_hook(non_repo)
    assert result == "error_not_a_repo"


# ── uninstall_hook ────────────────────────────────────────────────────────────


def test_uninstall_removes_block(git_repo):
    install_hook(git_repo)
    result = uninstall_hook(git_repo)
    assert result in ("removed", "deleted")
    assert not hook_status(git_repo)


def test_uninstall_deletes_file_when_only_content(git_repo):
    install_hook(git_repo)
    result = uninstall_hook(git_repo)
    assert result == "deleted"
    hook = Path(git_repo) / ".git" / "hooks" / "post-commit"
    assert not hook.exists()


def test_uninstall_keeps_other_hook_content(git_repo):
    hook = Path(git_repo) / ".git" / "hooks" / "post-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho 'keep me'\n")
    install_hook(git_repo)
    result = uninstall_hook(git_repo)
    assert result == "removed"
    content = hook.read_text()
    assert "keep me" in content
    assert HOOK_MARKER_START not in content


def test_uninstall_not_installed_returns_not_installed(git_repo):
    result = uninstall_hook(git_repo)
    assert result == "not_installed"


def test_uninstall_non_repo_returns_error(non_repo):
    result = uninstall_hook(non_repo)
    assert result == "error_not_a_repo"


# ── hook_status ───────────────────────────────────────────────────────────────


def test_status_false_before_install(git_repo):
    assert hook_status(git_repo) is False


def test_status_true_after_install(git_repo):
    install_hook(git_repo)
    assert hook_status(git_repo) is True


def test_status_false_after_uninstall(git_repo):
    install_hook(git_repo)
    uninstall_hook(git_repo)
    assert hook_status(git_repo) is False


# ── _strip_hook_block ─────────────────────────────────────────────────────────


def test_strip_removes_only_marked_block():
    content = (
        "#!/bin/sh\n"
        "echo before\n"
        f"{HOOK_MARKER_START}\n"
        "devmemory ingest --source git > /dev/null 2>&1 &\n"
        f"{HOOK_MARKER_END}\n"
        "echo after\n"
    )
    result = _strip_hook_block(content)
    assert "echo before" in result
    assert "echo after" in result
    assert HOOK_MARKER_START not in result
    assert "devmemory" not in result
