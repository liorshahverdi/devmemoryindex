import subprocess
import hashlib
import time
from datetime import datetime
from pathlib import Path

from core.schema import Memory
from core.embeddings import embed_batch
from core.config import get_git_paths
from connectors.base import Connector

# Skip file diffs larger than this — likely minified/generated files
_MAX_FILE_DIFF_CHARS = 8000

# TEMP: set to True to print per-step timing to stderr
_DIAG = True


def _t(label: str, start: float) -> float:
    now = time.perf_counter()
    if _DIAG:
        import sys
        print(f"  [diff diag] {label}: {now - start:.3f}s", file=sys.stderr, flush=True)
    return now


class DiffConnector(Connector):
    """Indexes per-file code diffs as git_diff memories."""

    name = "diff"

    def __init__(self, repo_paths: list[str] | None = None, commit_limit: int = 2):
        super().__init__()
        self.repo_paths = repo_paths or get_git_paths() or ["."]
        self.commit_limit = commit_limit

    def collect(self) -> int:
        count = 0
        for repo_path in self.repo_paths:
            count += self._index_repo(repo_path)
        return count

    def _index_repo(self, path: str) -> int:
        import sys
        count = 0
        t0 = time.perf_counter()

        result = subprocess.run(
            ["git", "-C", path, "log", "--pretty=format:%H|%s|%ct", "-n", str(self.commit_limit)],
            capture_output=True, text=True, timeout=30,
        )
        t0 = _t(f"git log ({path})", t0)

        if result.returncode != 0 or not result.stdout.strip():
            return 0

        repo_name = Path(path).resolve().name
        commits = result.stdout.strip().splitlines()
        print(f"  [diff diag] repo={repo_name}  commits={len(commits)}", file=sys.stderr, flush=True)

        for line in commits:
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            sha, subject, ts = parts
            t1 = time.perf_counter()

            diff_result = subprocess.run(
                ["git", "-C", path, "diff", "--unified=0", f"{sha}~1", sha],
                capture_output=True, text=True, timeout=30,
            )
            t1 = _t(f"  git diff {sha[:8]}", t1)

            if diff_result.returncode != 0 or not diff_result.stdout.strip():
                continue

            file_diffs = self._split_diff_by_file(diff_result.stdout)
            t1 = _t(f"  split ({len(file_diffs)} files, {len(diff_result.stdout)} chars)", t1)

            if not file_diffs:
                continue

            candidate_ids = [
                hashlib.sha256(f"{sha}|{repo_name}|{fp}".encode()).hexdigest()
                for fp, _ in file_diffs
            ]
            existing_ids = self._batch_existing(candidate_ids)
            t1 = _t(f"  batch_existing ({len(candidate_ids)} ids, {len(existing_ids)} known)", t1)

            new_memories: list[Memory] = []
            embed_texts: list[str] = []

            for (filepath, file_diff), mem_id in zip(file_diffs, candidate_ids):
                if mem_id in existing_ids:
                    continue
                if len(file_diff) > _MAX_FILE_DIFF_CHARS:
                    continue

                raw_text = self._redact(
                    f"commit: {sha[:8]} — {subject}\nfile: {filepath}\n\n{file_diff}"
                )
                change_lines = [
                    l for l in file_diff.splitlines()
                    if (l.startswith("+") or l.startswith("-"))
                    and not l.startswith("+++")
                    and not l.startswith("---")
                ]
                embed_text = f"{subject} {filepath}\n" + "\n".join(change_lines)
                suffix = Path(filepath).suffix.lstrip(".") or "file"
                new_memories.append(Memory(
                    id=mem_id,
                    type="git_diff",
                    summary=f"{subject[:100]} — {Path(filepath).name}",
                    raw_text=raw_text,
                    source=sha,
                    repo=repo_name,
                    timestamp=datetime.fromtimestamp(int(ts)),
                    tags=["git", "diff", suffix],
                    importance=0.6,
                ))
                embed_texts.append(embed_text[:512])

            t1 = _t(f"  build memories ({len(new_memories)} new)", t1)

            if not new_memories:
                continue

            vectors = embed_batch(embed_texts)
            t1 = _t(f"  embed_batch ({len(embed_texts)} texts)", t1)

            for memory, vector in zip(new_memories, vectors):
                self.store.add(memory, vector)
            t1 = _t(f"  store.add x{len(new_memories)}", t1)

            count += len(new_memories)

        return count

    def _batch_existing(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        try:
            escaped = "', '".join(i.replace("'", "''") for i in ids)
            results = (
                self.store.collection
                .search()
                .where(f"id IN ('{escaped}')")
                .limit(len(ids))
                .to_list()
            )
            return {r["id"] for r in results}
        except Exception:
            return set()

    def _split_diff_by_file(self, diff_text: str) -> list[tuple[str, str]]:
        files: list[tuple[str, str]] = []
        current_path: str | None = None
        current_lines: list[str] = []

        for line in diff_text.splitlines(keepends=True):
            if line.startswith("diff --git "):
                if current_path and current_lines:
                    files.append((current_path, "".join(current_lines)))
                parts = line.split(" b/", 1)
                current_path = parts[1].strip() if len(parts) > 1 else line.strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_path and current_lines:
            files.append((current_path, "".join(current_lines)))

        return files
