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

import fcntl
import tomllib
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "devmemory" / "config.toml"
_LOCK_PATH = CONFIG_PATH.parent / ".config.lock"


def load() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def save(data: dict) -> None:
    """Write config atomically under an exclusive file lock.

    Using fcntl.flock() ensures that concurrent CLI invocations (e.g., a daemon
    connector firing while the user runs `devmemory config add-code`) don't
    overwrite each other's changes.
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LOCK_PATH.touch(exist_ok=True)
    with open(_LOCK_PATH, "r") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            CONFIG_PATH.write_text(_to_toml(data))
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)


def _to_toml(data: dict) -> str:
    """Minimal TOML serializer for string/int/float/bool/list-of-strings structures."""
    lines = []
    for section, values in data.items():
        lines.append(f"[{section}]")
        for key, val in values.items():
            if isinstance(val, bool):
                # bool must be checked before int — bool is a subclass of int
                lines.append(f"{key} = {'true' if val else 'false'}")
            elif isinstance(val, int):
                lines.append(f"{key} = {val}")
            elif isinstance(val, float):
                lines.append(f"{key} = {val}")
            elif isinstance(val, list):
                if not val:
                    lines.append(f"{key} = []")
                else:
                    items = "\n".join(f'    "{v}",' for v in val)
                    lines.append(f"{key} = [\n{items}\n]")
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


# ── Filesystem-specific helpers ───────────────────────────────────────


def get_filesystem_dirs() -> list[str]:
    return load().get("filesystem", {}).get("scan_dirs", [])


def add_filesystem_dir(path: str) -> bool:
    """Add path to filesystem.scan_dirs. Returns False if already present."""
    data = load()
    data.setdefault("filesystem", {}).setdefault("scan_dirs", [])
    if path in data["filesystem"]["scan_dirs"]:
        return False
    data["filesystem"]["scan_dirs"].append(path)
    save(data)
    return True


def remove_filesystem_dir(path: str) -> bool:
    """Remove path from filesystem.scan_dirs. Returns False if not found."""
    data = load()
    dirs = data.get("filesystem", {}).get("scan_dirs", [])
    if path not in dirs:
        return False
    dirs.remove(path)
    data["filesystem"]["scan_dirs"] = dirs
    save(data)
    return True


# ── Meeting-specific helpers ──────────────────────────────────────────


def get_meeting_dirs() -> list[str]:
    return load().get("meeting", {}).get("scan_dirs", [])


def add_meeting_dir(path: str) -> bool:
    """Add path to meeting.scan_dirs. Returns False if already present."""
    data = load()
    data.setdefault("meeting", {}).setdefault("scan_dirs", [])
    if path in data["meeting"]["scan_dirs"]:
        return False
    data["meeting"]["scan_dirs"].append(path)
    save(data)
    return True


def remove_meeting_dir(path: str) -> bool:
    """Remove path from meeting.scan_dirs. Returns False if not found."""
    data = load()
    dirs = data.get("meeting", {}).get("scan_dirs", [])
    if path not in dirs:
        return False
    dirs.remove(path)
    data["meeting"]["scan_dirs"] = dirs
    save(data)
    return True


# ── User identity helpers ─────────────────────────────────────────


def get_user_name() -> str | None:
    """Return the configured user name for speaker attribution (e.g. "Lasha")."""
    return load().get("user", {}).get("name") or None


def get_user_aliases() -> list[str]:
    """Return the configured name aliases (e.g. ["L", "LS"]) for speaker matching."""
    return load().get("user", {}).get("aliases", [])


def set_user_identity(name: str, aliases: list[str] | None = None) -> None:
    """Persist [user] name (and optional aliases) to config.toml."""
    data = load()
    user_section = data.setdefault("user", {})
    user_section["name"] = name
    if aliases is not None:
        user_section["aliases"] = aliases
    save(data)


# ── API key helpers ───────────────────────────────────────────────


def get_api_key() -> str | None:
    return load().get("api", {}).get("key") or None


def set_api_key(key: str) -> None:
    data = load()
    data.setdefault("api", {})["key"] = key
    save(data)


def delete_api_key() -> None:
    data = load()
    data.get("api", {}).pop("key", None)
    save(data)


# ── LLM helpers ──────────────────────────────────────────────────────


def get_llm_config() -> dict:
    """Return the [llm] config section, with sensible defaults.

    Keys:
      backend  — "ollama" (default) or "llamacpp"
      model    — model name for Ollama (default: "mistral")
      url      — server URL override
    """
    return load().get("llm", {})


def set_llm_config(backend: str | None = None, model: str | None = None, url: str | None = None) -> None:
    """Persist one or more [llm] keys to config.toml."""
    data = load()
    llm = data.setdefault("llm", {})
    if backend is not None:
        llm["backend"] = backend
    if model is not None:
        llm["model"] = model
    if url is not None:
        llm["url"] = url
    save(data)


# ── Schedule helpers ──────────────────────────────────────────────────

_DEFAULT_INTERVALS: dict[str, int] = {
    "git": 600,        # 10 min
    "claude": 300,     # 5 min
    "terminal": 3600,  # 1 hour
    "markdown": 1800,  # 30 min
    "filesystem": 1800,  # 30 min
    "copilot": 600,    # 10 min
    "browser": 7200,   # 2 hours
    "meeting": 3600,   # 1 hour
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
