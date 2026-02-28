"""
Copilot Connector — indexes GitHub Copilot Chat conversation history.

VS Code stores chat sessions as JSONL files in per-workspace storage:

  ~/Library/Application Support/Code/User/workspaceStorage/
      {workspace_hash}/chatSessions/{session_id}.jsonl

Each .jsonl file contains incremental updates:
  kind=0  initial session state
  kind=1  single-key patch  {"k": ["requests", 0, "result"], "v": ...}
  kind=2  array-append      {"k": ["requests"], "v": [full_array]}

Assistant text appears in kind=2 lines where k ends with "response",
as parts that have a "value" string field (inline text) or "kind"=="thinking".

Memory fields:
  type        "copilot_chat"
  summary     first 200 chars of response (title + first text chunk)
  raw_text    full text of the response (redacted, up to 3000 chars)
  source      path to the .jsonl file
  repo        detected from workspace.json if present
  timestamp   session file mtime
  importance  0.75
  tags        ["copilot", "agent"]
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from connectors.base import Connector
from core.embeddings import embed
from core.schema import Memory

MIN_RESPONSE_LEN = 100  # skip very short tool-only responses

_VSCODE_WORKSPACE_STORAGE = (
    Path.home() / "Library" / "Application Support" / "Code" / "User" / "workspaceStorage"
)
_VSCODE_INSIDERS_WORKSPACE_STORAGE = (
    Path.home() / "Library" / "Application Support" / "Code - Insiders" / "User" / "workspaceStorage"
)


def _find_chat_session_dirs() -> list[Path]:
    """Return all chatSessions/ directories across workspace storage."""
    dirs: list[Path] = []
    for base in (_VSCODE_WORKSPACE_STORAGE, _VSCODE_INSIDERS_WORKSPACE_STORAGE):
        if not base.is_dir():
            continue
        for ws_dir in base.iterdir():
            cs = ws_dir / "chatSessions"
            if cs.is_dir():
                dirs.append(cs)
    return dirs


def _workspace_folder(chat_sessions_dir: Path) -> str | None:
    """Read the workspace.json next to chatSessions to get the folder path."""
    try:
        ws_json = chat_sessions_dir.parent / "workspace.json"
        data = json.loads(ws_json.read_text())
        folder = data.get("folder", "")
        # Strip file:// prefix
        if folder.startswith("file://"):
            folder = folder[7:]
        return folder or None
    except Exception:
        return None


class CopilotConnector(Connector):
    name = "copilot"

    def collect(self) -> int:
        dirs = _find_chat_session_dirs()
        if not dirs:
            return 0
        count = 0
        for cs_dir in dirs:
            repo = _workspace_folder(cs_dir)
            for jsonl_file in sorted(cs_dir.glob("*.jsonl")):
                try:
                    count += self._parse_session(jsonl_file, repo=repo)
                except Exception:
                    pass
        return count

    def _parse_session(self, path: Path, repo: str | None = None) -> int:
        responses = _extract_responses_from_jsonl(path)
        if not responses:
            return 0

        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        added = 0

        for text in responses:
            text = text.strip()
            if len(text) < MIN_RESPONSE_LEN:
                continue

            mem_id = hashlib.sha256(text[:500].encode()).hexdigest()
            if self.store.exists(mem_id):
                continue

            summary = text[:200].replace("\n", " ")
            memory = Memory(
                id=mem_id,
                type="copilot_chat",
                summary=summary,
                raw_text=self._redact(text[:3000]),
                source=str(path),
                repo=repo,
                timestamp=mtime,
                tags=["copilot", "agent"],
                importance=0.75,
            )
            self.store.add(memory, embed(summary[:512]))
            added += 1

        return added


# ── JSONL parsing ────────────────────────────────────────────────────────────


def _extract_responses_from_jsonl(path: Path) -> list[str]:
    """
    Parse a Copilot Chat .jsonl file and return assistant response texts.

    The format is an incremental log:
      kind=0  full initial state  {"kind": 0, "v": {...}}
      kind=1  patch a field       {"kind": 1, "k": ["requests", 0, "result"], "v": ...}
      kind=2  replace a field     {"kind": 2, "k": ["requests"], "v": [...]}

    We watch for kind=2 lines whose key path ends with "response" — those
    contain the list of response parts for each request/turn.
    """
    responses: list[str] = []

    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return responses

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        if entry.get("kind") != 2:
            continue

        k = entry.get("k", [])
        if not isinstance(k, list) or not k:
            continue

        # We want keys that end with "response"
        if k[-1] != "response":
            continue

        parts = entry.get("v", [])
        if not isinstance(parts, list):
            continue

        text = _parts_to_text(parts)
        if text:
            responses.append(text)

    return responses


def _parts_to_text(parts: list) -> str:
    """
    Concatenate text from response part objects.

    VS Code response parts we care about:
      - {"value": "...", "supportThemeIcons": ...}   → inline markdown text
      - {"kind": "thinking", "value": "..."}          → model reasoning

    Parts we skip:
      - {"kind": "toolInvocationSerialized", ...}
      - {"kind": "inlineReference", ...}
      - empty thinking parts (value == "")
    """
    chunks: list[str] = []

    for part in parts:
        if not isinstance(part, dict):
            continue

        kind = part.get("kind")

        if kind == "toolInvocationSerialized":
            continue
        if kind == "inlineReference":
            continue

        value = part.get("value", "")
        if not isinstance(value, str) or not value.strip():
            continue

        chunks.append(value)

    return "".join(chunks).strip()
