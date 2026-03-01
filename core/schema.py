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
    times_retrieved: int = 0    # how many times this memory appeared in search results
    times_accessed: int = 0     # how many times get_memory was called for it
    status: str = "active"      # "active" | "deprecated"
    deprecation_reason: str = ""  # reason string when status == "deprecated"