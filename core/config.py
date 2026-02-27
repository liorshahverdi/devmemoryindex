"""
Persistent configuration for DevMemoryIndex.

Stored at ~/.config/devmemory/config.toml

Example:
    [git]
    repo_paths = [
        "/Users/you/projects/myapp",
        "/Users/you/projects/other",
    ]

    [markdown]
    scan_dirs = [
        "/Users/you/notes",
        "/Users/you/obsidian-vault",
    ]

    [schedule]
    git = 600
    claude = 300
    terminal = 3600
    markdown = 1800
"""

import tomllib
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "devmemory" / "config.toml"


def load() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def save(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(_to_toml(data))


def _to_toml(data: dict) -> str:
    """Minimal TOML serializer for string/int/list-of-strings structures."""
    lines = []
    for section, values in data.items():
        lines.append(f"[{section}]")
        for key, val in values.items():
            if isinstance(val, list):
                if not val:
                    lines.append(f"{key} = []")
                else:
                    items = "\n".join(f'    "{v}",' for v in val)
                    lines.append(f"{key} = [\n{items}\n]")
            elif isinstance(val, int):
                lines.append(f"{key} = {val}")
            else:
                lines.append(f'{key} = "{val}"')
        lines.append("")
    return "\n".join(lines)


# ── Git-specific helpers ──────────────────────────────────────────────


def get_git_paths() -> list[str]:
    return load().get("git", {}).get("repo_paths", [])


def add_git_path(path: str) -> bool:
    """Add path to git.repo_paths. Returns False if already present."""
    data = load()
    data.setdefault("git", {}).setdefault("repo_paths", [])
    if path in data["git"]["repo_paths"]:
        return False
    data["git"]["repo_paths"].append(path)
    save(data)
    return True


def remove_git_path(path: str) -> bool:
    """Remove path from git.repo_paths. Returns False if not found."""
    data = load()
    paths = data.get("git", {}).get("repo_paths", [])
    if path not in paths:
        return False
    paths.remove(path)
    data["git"]["repo_paths"] = paths
    save(data)
    return True


# ── Markdown-specific helpers ─────────────────────────────────────────


def get_markdown_dirs() -> list[str]:
    return load().get("markdown", {}).get("scan_dirs", [])


def add_markdown_dir(path: str) -> bool:
    """Add path to markdown.scan_dirs. Returns False if already present."""
    data = load()
    data.setdefault("markdown", {}).setdefault("scan_dirs", [])
    if path in data["markdown"]["scan_dirs"]:
        return False
    data["markdown"]["scan_dirs"].append(path)
    save(data)
    return True


def remove_markdown_dir(path: str) -> bool:
    """Remove path from markdown.scan_dirs. Returns False if not found."""
    data = load()
    dirs = data.get("markdown", {}).get("scan_dirs", [])
    if path not in dirs:
        return False
    dirs.remove(path)
    data["markdown"]["scan_dirs"] = dirs
    save(data)
    return True


# ── Schedule helpers ──────────────────────────────────────────────────

_DEFAULT_INTERVALS: dict[str, int] = {
    "git": 600,       # 10 min
    "claude": 300,    # 5 min
    "terminal": 3600, # 1 hour
    "markdown": 1800, # 30 min
}

CONNECTOR_NAMES = list(_DEFAULT_INTERVALS.keys())


def get_connector_interval(name: str) -> int:
    """Return the ingest interval (seconds) for a connector, with defaults."""
    return load().get("schedule", {}).get(name, _DEFAULT_INTERVALS.get(name, 600))


def set_connector_interval(name: str, seconds: int) -> None:
    """Persist a per-connector ingest interval to config."""
    data = load()
    data.setdefault("schedule", {})[name] = seconds
    save(data)


def get_all_intervals() -> dict[str, int]:
    """Return {connector: interval_seconds} for all known connectors."""
    stored = load().get("schedule", {})
    return {name: stored.get(name, default) for name, default in _DEFAULT_INTERVALS.items()}
