import hashlib
import re
from datetime import datetime
from pathlib import Path

from connectors.base import Connector
from core.embeddings import embed
from core.schema import Memory


class TerminalConnector(Connector):
    name = "terminal"

    HISTORY_FILES = [
        Path.home() / ".zsh_history",
        Path.home() / ".bash_history",
    ]

    MIN_CMD_LENGTH = 5

    IGNORE_PREFIXES = [
        "cd ", "ls", "ll", "pwd", "clear", "exit", "echo",
        "cat ", "man ", "which ", "history",
    ]

    def collect(self) -> int:
        count = 0
        for hist_file in self.HISTORY_FILES:
            if hist_file.exists():
                count += self._index_history(hist_file)
        return count

    def _index_history(self, path: Path) -> int:
        count = 0
        lines = path.read_text(errors="ignore").splitlines()

        # Walk in reverse, collect last 500 unique meaningful commands
        seen = set()
        commands = []
        for line in reversed(lines):
            cmd = self._parse_line(line)
            if not cmd:
                continue
            if len(cmd) < self.MIN_CMD_LENGTH:
                continue
            if any(cmd.startswith(p) for p in self.IGNORE_PREFIXES):
                continue
            if cmd not in seen:
                seen.add(cmd)
                commands.append(cmd)
            if len(commands) >= 500:
                break

        for cmd in commands:
            mem_id = hashlib.sha256(cmd.encode()).hexdigest()
            if self.store.exists(mem_id):
                continue

            memory = Memory(
                id=mem_id,
                type="terminal_command",
                summary=cmd[:200],
                raw_text=cmd,
                source=str(path),
                repo=None,
                timestamp=datetime.utcnow(),
                tags=["terminal"],
                importance=self._estimate_importance(cmd),
            )

            self.store.add(memory, embed(memory.summary))
            count += 1

        return count

    def _parse_line(self, line: str) -> str | None:
        """Handle both plain history and zsh extended format (': timestamp:0;command')."""
        line = line.strip()
        match = re.match(r'^:\s*\d+:\d+;(.+)$', line)
        if match:
            return match.group(1).strip()
        return line if line else None

    def _estimate_importance(self, cmd: str) -> float:
        c = cmd.lower()
        if any(w in c for w in ["docker", "kubectl", "terraform", "ansible"]):
            return 0.8
        if any(w in c for w in ["git rebase", "git cherry-pick", "git bisect"]):
            return 0.7
        if any(w in c for w in ["pip install", "npm install", "brew install", "uv add", "uv pip install"]):
            return 0.6
        return 0.4
