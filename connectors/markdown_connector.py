"""
Markdown Connector — indexes .md files from configured scan directories.

Each file is split into chunks at H2 (##) headings. Each chunk becomes a
separate memory so that search can surface specific sections rather than
whole files.

Memory fields:
  type        "markdown_note"
  summary     "filename > section title" (or just filename for the intro chunk)
  raw_text    chunk content (redacted)
  repo        inferred from nearest .git parent directory, or None
  timestamp   file mtime
  importance  0.7 by default; bumped to 0.85 for files tagged "important"
  tags        ["markdown"] + any YAML frontmatter tags

Configuration:
  devmemory config add-notes ~/notes
  devmemory config add-notes ~/vault
"""

import hashlib
import re
from datetime import datetime
from pathlib import Path

import core.config as cfg
from connectors.base import Connector
from core.embeddings import embed
from core.schema import Memory

MIN_CHUNK_LEN = 80  # chars — skip stubs / empty sections
MAX_CHUNK_LEN = 2000  # chars — truncate very long chunks before embedding


class MarkdownConnector(Connector):
    name = "markdown"

    def collect(self) -> int:
        dirs = cfg.get_markdown_dirs()
        if not dirs:
            return 0

        added = 0
        for dir_path in dirs:
            root = Path(dir_path).expanduser().resolve()
            if not root.is_dir():
                continue
            for md_file in sorted(root.rglob("*.md")):
                # skip hidden directories (.git, .obsidian, node_modules, etc.)
                if any(part.startswith(".") for part in md_file.parts):
                    continue
                if "node_modules" in md_file.parts:
                    continue
                try:
                    added += self._ingest_file(md_file)
                except Exception:
                    pass  # skip unreadable files silently
        return added

    def _ingest_file(self, path: Path) -> int:
        text = path.read_text(errors="ignore")
        frontmatter, body = _parse_frontmatter(text)

        tags = frontmatter.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        elif not isinstance(tags, list):
            tags = []

        title_override = frontmatter.get("title", "").strip()
        file_title = title_override or path.stem.replace("-", " ").replace("_", " ")

        importance = 0.85 if "important" in tags else 0.7

        repo = _infer_repo(path)
        mtime = datetime.fromtimestamp(path.stat().st_mtime)

        chunks = _chunk_by_h2(body, file_title)

        added = 0
        for chunk_title, chunk_text in chunks:
            chunk_text = chunk_text.strip()
            if len(chunk_text) < MIN_CHUNK_LEN:
                continue

            chunk_text = self._redact(chunk_text)
            mem_id = hashlib.sha256(
                f"{path}|{chunk_title}|{chunk_text[:500]}".encode()
            ).hexdigest()

            if self.store.exists(mem_id):
                continue

            embed_input = f"{chunk_title} {chunk_text[:MAX_CHUNK_LEN]}"
            memory = Memory(
                id=mem_id,
                type="markdown_note",
                summary=chunk_title[:200],
                raw_text=chunk_text[:MAX_CHUNK_LEN],
                source="markdown",
                repo=repo,
                timestamp=mtime,
                tags=tags + ["markdown"],
                importance=importance,
            )
            self.store.add(memory, embed(embed_input))
            added += 1
        return added


# ── Helpers ───────────────────────────────────────────────────────────


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Strip YAML frontmatter block. Returns (parsed_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    parsed: dict = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        # handle YAML list shorthand: tags: [foo, bar]
        if val.startswith("[") and val.endswith("]"):
            parsed[key] = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",") if v.strip()]
        else:
            parsed[key] = val
    return parsed, body


def _chunk_by_h2(body: str, file_title: str) -> list[tuple[str, str]]:
    """
    Split markdown body into chunks at ## headings.

    Returns list of (chunk_title, chunk_text) pairs:
      - Intro chunk (content before first ##): title = file_title
      - Each section: title = "file_title > Section Heading"
    """
    # Split on lines that start with ##  (not ### or deeper)
    parts = re.split(r"(?m)^(##\s+.+)$", body)
    chunks: list[tuple[str, str]] = []

    # parts[0] is content before the first ##
    intro = parts[0].strip()
    if intro:
        chunks.append((file_title, intro))

    # Walk remaining pairs: [heading_line, content, heading_line, content, ...]
    i = 1
    while i < len(parts) - 1:
        heading_line = parts[i].lstrip("#").strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        chunk_title = f"{file_title} > {heading_line}"
        if content:
            chunks.append((chunk_title, content))
        i += 2

    # If no ## headings were found and intro was empty, use the whole body
    if not chunks and body.strip():
        chunks.append((file_title, body.strip()))

    return chunks


def _infer_repo(path: Path) -> str | None:
    """Walk up from path to find the nearest .git directory. Returns dir name."""
    for parent in path.parents:
        if (parent / ".git").exists():
            return parent.name
    return None
