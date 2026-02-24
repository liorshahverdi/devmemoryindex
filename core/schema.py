from dataclasses import dataclass
from datetime import datetime
from typing import List

@dataclass
class Memory:
    id: str                     # Unique ID (UUID or hash)
    type: str                   # "git_commit", "terminal_command", "agent_solution", "copilot_chat", "file_content"
    summary: str                # Short human-readable summary (~200 characters)
    raw_text: str               # Full text
    source: str                 # filepath, repo, agent name, etc.
    repo: str | None            # Repo name for git commits
    timestamp: datetime
    tags: List[str]             # Optional keywords
    importance: float = 0.5     # 0-1, used for ranking