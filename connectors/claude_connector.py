"""
Claude Code Connector

Indexes assistant responses from Claude Code conversation logs as searchable memories.

Storage location: ~/.claude/projects/<project-dir>/<session-uuid>.jsonl
Format: newline-delimited JSON. Each line is one event. Assistant turns have:
  {
    "type": "assistant",
    "message": {"role": "assistant", "content": <str or list of blocks>},
    "cwd": "/path/to/project",
    "timestamp": "2026-02-27T02:45:52.520Z",
    "sessionId": "<uuid>"
  }
  Content is either a plain string or a list of blocks where text blocks have
  {"type": "text", "text": "..."}.

Only substantive assistant responses (>= 150 chars of text) are indexed.
Short replies ("Done.", "ok", etc.) are skipped.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from connectors.base import Connector
from core.embeddings import embed
from core.schema import Memory

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
MIN_TEXT_LENGTH = 150  # skip trivial one-liners


def _extract_text(content) -> str:
    """Extract plain text from a message content field (str or block list)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    return ""


def _repo_from_cwd(cwd: str) -> str | None:
    """Derive repo name from the session's working directory."""
    if not cwd:
        return None
    return Path(cwd).name or None


class ClaudeConnector(Connector):
    name = "claude"

    def __init__(self, projects_dir: Path = CLAUDE_PROJECTS_DIR):
        super().__init__()
        self.projects_dir = projects_dir

    def collect(self) -> int:
        if not self.projects_dir.exists():
            return 0
        count = 0
        for jsonl_file in self.projects_dir.rglob("*.jsonl"):
            count += self._index_session(jsonl_file)
        return count

    def _index_session(self, path: Path) -> int:
        count = 0
        try:
            lines = path.read_text(errors="ignore").splitlines()
        except Exception:
            return 0

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("type") != "assistant":
                continue
            message = obj.get("message", {})
            if message.get("role") != "assistant":
                continue

            text = self._redact(_extract_text(message.get("content", "")))
            if len(text) < MIN_TEXT_LENGTH:
                continue

            mem_id = hashlib.sha256(text[:500].encode()).hexdigest()
            if self.store.exists(mem_id):
                continue

            # Parse ISO timestamp from the event; fall back to file mtime
            ts_raw = obj.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                ts = datetime.fromtimestamp(path.stat().st_mtime)

            repo = _repo_from_cwd(obj.get("cwd", ""))

            memory = Memory(
                id=mem_id,
                type="agent_solution",
                summary=text[:200],
                raw_text=text[:2000],
                source=str(path),
                repo=repo,
                timestamp=ts,
                tags=["claude", "agent"],
                importance=0.9,
            )

            self.store.add(memory, embed(memory.summary))
            count += 1

        return count
