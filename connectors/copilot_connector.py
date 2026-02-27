"""
Copilot Connector — indexes GitHub Copilot Chat conversation history.

Scans VS Code's extension storage directory for Copilot Chat JSON session
files and extracts assistant responses. Best-effort: silently returns 0 if
the storage directory doesn't exist or contains an unrecognised format.

Storage location (macOS):
  ~/Library/Application Support/Code/User/globalStorage/github.copilot-chat/

Memory fields:
  type        "copilot_chat"
  summary     first 200 chars of assistant response
  raw_text    response content (redacted, up to 3000 chars)
  source      path to the session JSON file
  repo        None (Copilot sessions are not repo-scoped)
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

MIN_RESPONSE_LEN = 100  # skip very short acknowledgements

# Extension storage paths per platform
_VSCODE_GLOBAL_STORAGE = Path.home() / "Library" / "Application Support" / "Code" / "User" / "globalStorage"
_VSCODE_INSIDERS_STORAGE = Path.home() / "Library" / "Application Support" / "Code - Insiders" / "User" / "globalStorage"
_COPILOT_DIR_NAME = "github.copilot-chat"


def _find_copilot_dirs() -> list[Path]:
    candidates = []
    for base in (_VSCODE_GLOBAL_STORAGE, _VSCODE_INSIDERS_STORAGE):
        d = base / _COPILOT_DIR_NAME
        if d.is_dir():
            candidates.append(d)
    return candidates


class CopilotConnector(Connector):
    name = "copilot"

    def collect(self) -> int:
        dirs = _find_copilot_dirs()
        if not dirs:
            return 0
        count = 0
        for d in dirs:
            for json_file in sorted(d.rglob("*.json")):
                try:
                    count += self._parse_session(json_file)
                except Exception:
                    pass
        return count

    def _parse_session(self, path: Path) -> int:
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except (json.JSONDecodeError, OSError):
            return 0

        messages = _extract_assistant_messages(data)
        mtime = datetime.fromtimestamp(path.stat().st_mtime)

        added = 0
        for msg in messages:
            msg = msg.strip()
            if len(msg) < MIN_RESPONSE_LEN:
                continue

            mem_id = hashlib.sha256(msg[:500].encode()).hexdigest()
            if self.store.exists(mem_id):
                continue

            summary = msg[:200].replace("\n", " ")
            memory = Memory(
                id=mem_id,
                type="copilot_chat",
                summary=summary,
                raw_text=self._redact(msg[:3000]),
                source=str(path),
                repo=None,
                timestamp=mtime,
                tags=["copilot", "agent"],
                importance=0.75,
            )
            self.store.add(memory, embed(summary[:512]))
            added += 1
        return added


# ── Helpers ────────────────────────────────────────────────────────────


def _extract_assistant_messages(data, _depth: int = 0) -> list[str]:
    """
    Recursively extract assistant/model text from any Copilot JSON structure.

    Handles several observed formats:
      - {"role": "assistant", "content": "..."}
      - {"role": "model", "parts": [{"text": "..."}]}
      - {"messages": [...]}
      - {"turns": [...]} / {"responses": [...]} / {"conversations": [...]}
      - top-level list of session objects
    """
    if _depth > 8:  # guard against deeply nested structures
        return []

    messages: list[str] = []

    if isinstance(data, list):
        for item in data:
            messages.extend(_extract_assistant_messages(item, _depth + 1))

    elif isinstance(data, dict):
        role = data.get("role", "")

        # Pattern: {"role": "assistant"|"model", "content": str}
        if role in ("assistant", "model"):
            content = data.get("content", "")
            if isinstance(content, str) and content.strip():
                messages.append(content.strip())
            elif isinstance(content, list):
                # {"content": [{"type": "text", "text": "..."}]}
                text = " ".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ).strip()
                if text:
                    messages.append(text)

        # Pattern: {"role": "model", "parts": [{"text": "..."}]}
        if role == "model" and "parts" in data:
            text = " ".join(
                p.get("text", "") for p in data["parts"]
                if isinstance(p, dict)
            ).strip()
            if text:
                messages.append(text)

        # Recurse into known list keys
        for key in ("messages", "turns", "responses", "conversations",
                    "entries", "items", "history", "chatHistory"):
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    messages.extend(_extract_assistant_messages(item, _depth + 1))

    return messages
