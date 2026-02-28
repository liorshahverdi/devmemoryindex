"""
Git hook management for DevMemoryIndex.

Installs a post-commit hook that runs `devmemory ingest --source git`
in the background after every commit, so new commits are indexed
immediately instead of waiting for the daemon poll cycle.

The hook block is wrapped in marker comments so it can be safely
appended to existing hooks and removed without disturbing other content.
"""

import os
import stat
from pathlib import Path

HOOK_MARKER_START = "# devmemory-hook-start"
HOOK_MARKER_END   = "# devmemory-hook-end"

_HOOK_BLOCK = """\
{start}
devmemory ingest --source git > /dev/null 2>&1 &
{end}
""".format(start=HOOK_MARKER_START, end=HOOK_MARKER_END)

_HOOK_SHEBANG = "#!/bin/sh\n"


def _hook_path(repo_path: str) -> Path:
    return Path(repo_path) / ".git" / "hooks" / "post-commit"


def install_hook(repo_path: str) -> str:
    """Install the devmemory post-commit hook for the given repo.

    Returns one of:
      "installed"          — hook file created fresh
      "appended"           — devmemory block added to existing hook
      "already_installed"  — block already present, nothing changed
      "error_not_a_repo"   — no .git directory found at repo_path
    """
    git_dir = Path(repo_path) / ".git"
    if not git_dir.is_dir():
        return "error_not_a_repo"

    hook_file = _hook_path(repo_path)

    if hook_file.exists():
        content = hook_file.read_text()
        if HOOK_MARKER_START in content:
            return "already_installed"
        # Append to existing hook, separated by a blank line
        new_content = content.rstrip("\n") + "\n\n" + _HOOK_BLOCK
        hook_file.write_text(new_content)
        _ensure_executable(hook_file)
        return "appended"
    else:
        hook_file.parent.mkdir(parents=True, exist_ok=True)
        hook_file.write_text(_HOOK_SHEBANG + "\n" + _HOOK_BLOCK)
        _ensure_executable(hook_file)
        return "installed"


def uninstall_hook(repo_path: str) -> str:
    """Remove the devmemory block from the post-commit hook.

    Returns one of:
      "removed"            — block stripped; file kept (other content remains)
      "deleted"            — block was the only content; file removed
      "not_installed"      — devmemory block not found in hook
      "error_not_a_repo"   — no .git directory found
    """
    git_dir = Path(repo_path) / ".git"
    if not git_dir.is_dir():
        return "error_not_a_repo"

    hook_file = _hook_path(repo_path)
    if not hook_file.exists():
        return "not_installed"

    content = hook_file.read_text()
    if HOOK_MARKER_START not in content:
        return "not_installed"

    cleaned = _strip_hook_block(content)

    # If nothing meaningful remains (just a shebang or whitespace), delete the file
    stripped = cleaned.replace(_HOOK_SHEBANG, "").strip()
    if not stripped:
        hook_file.unlink()
        return "deleted"

    hook_file.write_text(cleaned)
    return "removed"


def hook_status(repo_path: str) -> bool:
    """Return True if the devmemory hook block is present in the repo's post-commit hook."""
    hook_file = _hook_path(repo_path)
    if not hook_file.exists():
        return False
    return HOOK_MARKER_START in hook_file.read_text()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _ensure_executable(path: Path) -> None:
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _strip_hook_block(content: str) -> str:
    """Remove lines from HOOK_MARKER_START through HOOK_MARKER_END (inclusive)."""
    lines = content.splitlines(keepends=True)
    result = []
    inside = False
    for line in lines:
        if line.strip() == HOOK_MARKER_START:
            inside = True
            continue
        if line.strip() == HOOK_MARKER_END:
            inside = False
            continue
        if not inside:
            result.append(line)
    # Collapse multiple trailing blank lines left by the removal
    text = "".join(result)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text
