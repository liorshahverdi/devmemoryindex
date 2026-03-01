import subprocess
import hashlib
from datetime import datetime
from pathlib import Path
from core.schema import Memory
from core.embeddings import embed
from core.config import get_git_paths
from connectors.base import Connector


class GitConnector(Connector):
    name = "git"

    def __init__(self, repo_paths: list[str] | None = None):
        super().__init__()
        self.repo_paths = repo_paths or get_git_paths() or ["."]

    def collect(self) -> int:
        count = 0
        for repo_path in self.repo_paths:
            count += self._index_repo(repo_path)
        return count

    def _index_repo(self, path: str) -> int:
        result = subprocess.run(
            ["git", "-C", path, "log",
             "--pretty=format:%H|%s|%an|%ct",
             "-n", "100"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return 0

        repo_name = Path(path).resolve().name

        # Pre-filter: compute all candidate IDs and drop already-stored ones
        # in a single batch check before fetching any commit details.
        candidates = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            sha, subject, author, ts = parts
            mem_id = hashlib.sha256((sha + repo_name).encode()).hexdigest()
            candidates.append((mem_id, sha, subject, author, ts))

        existing = self.store._batch_existing_ids([c[0] for c in candidates])
        new_candidates = [c for c in candidates if c[0] not in existing]

        if not new_candidates:
            return 0

        memories: list[Memory] = []
        vectors: list[list] = []

        for mem_id, sha, subject, author, ts in new_candidates:
            body_result = subprocess.run(
                ["git", "-C", path, "log", "-1", "--format=%b", sha],
                capture_output=True, text=True
            )
            body = body_result.stdout.strip() if body_result.returncode == 0 else ""

            diff_result = subprocess.run(
                ["git", "-C", path, "diff", "--stat", f"{sha}~1", sha],
                capture_output=True, text=True
            )
            diff_summary = diff_result.stdout.strip()[:500] if diff_result.returncode == 0 else ""

            raw_text = self._redact(
                f"{subject}\n\n{body}\n\nAuthor: {author}\nFiles changed:\n{diff_summary}".strip()
            )

            memory = Memory(
                id=mem_id,
                type="git_commit",
                summary=subject[:200],
                raw_text=raw_text,
                source=sha,
                repo=repo_name,
                timestamp=datetime.fromtimestamp(int(ts)),
                tags=["git"],
                importance=self._estimate_importance(subject),
            )

            embed_text = f"{subject}\n{body}".strip() if body else subject
            memories.append(memory)
            vectors.append(embed(embed_text[:512]))

        return self.store.add_batch(memories, vectors)

    def _estimate_importance(self, message: str) -> float:
        msg_lower = message.lower()
        if any(word in msg_lower for word in ["fix", "bug", "patch", "hotfix"]):
            return 0.9
        if any(word in msg_lower for word in ["feat", "add", "implement"]):
            return 0.7
        if any(word in msg_lower for word in ["refactor", "clean", "rename"]):
            return 0.5
        if any(word in msg_lower for word in ["docs", "readme", "comment"]):
            return 0.5
        return 0.5
