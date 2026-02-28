import subprocess
import hashlib
from datetime import datetime
from pathlib import Path

from core.schema import Memory
from core.embeddings import embed
from core.config import get_git_paths
from connectors.base import Connector


class DiffConnector(Connector):
    """Indexes per-file code diffs as git_diff memories.

    Unlike GitConnector (which indexes commit messages), DiffConnector indexes
    the actual line-level changes so you can search by *what changed*, not just
    why. Enables queries like "why did we remove Redis?" or "what touched auth.py?".

    One memory per changed file per commit. Embed text uses only +/- lines
    (not context) for maximum signal density.
    """

    name = "diff"

    def __init__(self, repo_paths: list[str] | None = None, commit_limit: int = 50):
        super().__init__()
        self.repo_paths = repo_paths or get_git_paths() or ["."]
        self.commit_limit = commit_limit

    def collect(self) -> int:
        count = 0
        for repo_path in self.repo_paths:
            count += self._index_repo(repo_path)
        return count

    def _index_repo(self, path: str) -> int:
        count = 0
        result = subprocess.run(
            ["git", "-C", path, "log", "--pretty=format:%H|%s|%ct", "-n", str(self.commit_limit)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return 0

        repo_name = Path(path).resolve().name

        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            sha, subject, ts = parts

            diff_result = subprocess.run(
                ["git", "-C", path, "diff", "--unified=3", f"{sha}~1", sha],
                capture_output=True, text=True, timeout=30,
            )
            if diff_result.returncode != 0 or not diff_result.stdout.strip():
                continue

            for filepath, file_diff in self._split_diff_by_file(diff_result.stdout):
                mem_id = hashlib.sha256(
                    f"{sha}|{repo_name}|{filepath}".encode()
                ).hexdigest()

                if self.store.exists(mem_id):
                    continue

                raw_text = self._redact(
                    f"commit: {sha[:8]} — {subject}\nfile: {filepath}\n\n{file_diff}"
                )

                # Embed only the changed lines (+/-) for signal density.
                # Exclude the +++ / --- header lines which are just filenames.
                change_lines = [
                    l for l in file_diff.splitlines()
                    if (l.startswith("+") or l.startswith("-"))
                    and not l.startswith("+++")
                    and not l.startswith("---")
                ]
                embed_text = f"{subject} {filepath}\n" + "\n".join(change_lines)

                suffix = Path(filepath).suffix.lstrip(".") or "file"
                memory = Memory(
                    id=mem_id,
                    type="git_diff",
                    summary=f"{subject[:100]} — {Path(filepath).name}",
                    raw_text=raw_text,
                    source=sha,
                    repo=repo_name,
                    timestamp=datetime.fromtimestamp(int(ts)),
                    tags=["git", "diff", suffix],
                    importance=0.6,
                )
                vector = embed(embed_text[:512])
                self.store.add(memory, vector)
                count += 1

        return count

    def _split_diff_by_file(self, diff_text: str) -> list[tuple[str, str]]:
        """Split a full git diff into (filepath, per_file_diff) pairs."""
        files: list[tuple[str, str]] = []
        current_path: str | None = None
        current_lines: list[str] = []

        for line in diff_text.splitlines(keepends=True):
            if line.startswith("diff --git "):
                if current_path and current_lines:
                    files.append((current_path, "".join(current_lines)))
                # "diff --git a/foo/bar.py b/foo/bar.py" → "foo/bar.py"
                parts = line.split(" b/", 1)
                current_path = parts[1].strip() if len(parts) > 1 else line.strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_path and current_lines:
            files.append((current_path, "".join(current_lines)))

        return files
