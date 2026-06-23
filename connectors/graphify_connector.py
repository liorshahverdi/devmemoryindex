"""Graphify connector — imports existing Graphify graph outputs.

Phase 1 is intentionally read-only and optional: it ingests Graphify's
``graphify-out/GRAPH_REPORT.md`` and ``graphify-out/graph.json`` artifacts into
DevMemoryIndex memories, but does not invoke Graphify, create EdgeStore links,
run daemon automation, or expose MCP tools.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from connectors.base import Connector
from core.embeddings import embed_batch
from core.schema import Memory


class GraphifyOutputMissingError(FileNotFoundError):
    """Raised when the expected Graphify output files are missing."""


def _deterministic_node_id(repo: str, graphify_node_id: str) -> str:
    return hashlib.sha256(f"graphify-node:{repo}:{graphify_node_id}".encode()).hexdigest()


def _deterministic_report_id(repo: str, heading: str, source: Path) -> str:
    return hashlib.sha256(f"graphify-report:{repo}:{source.resolve()}:{heading}".encode()).hexdigest()


class GraphifyConnector(Connector):
    """Import Graphify report sections and graph nodes as searchable memories."""

    name = "graphify"

    def __init__(
        self,
        path: str | Path = ".",
        *,
        repo: str | None = None,
        graph: str | Path | None = None,
        report: str | Path | None = None,
        no_report: bool = False,
        no_nodes: bool = False,
        min_degree: int = 0,
        dry_run: bool = False,
    ):
        super().__init__()
        self.path = Path(path).expanduser().resolve()
        self.repo = repo or _infer_repo(self.path)
        out_dir = self.path / "graphify-out"
        self.graph_path = Path(graph).expanduser().resolve() if graph else out_dir / "graph.json"
        self.report_path = Path(report).expanduser().resolve() if report else out_dir / "GRAPH_REPORT.md"
        self.no_report = no_report
        self.no_nodes = no_nodes
        self.min_degree = min_degree
        self.dry_run = dry_run
        self.last_stats = self._new_stats()

    @staticmethod
    def _new_stats() -> dict:
        return {
            "repo": None,
            "reports": 0,
            "nodes": 0,
            "skipped": Counter(),
            "errors": 0,
            "dry_run": False,
        }

    def collect(self) -> int:
        self.last_stats = self._new_stats()
        self.last_stats["repo"] = self.repo
        self.last_stats["dry_run"] = self.dry_run
        self._validate_inputs()

        memories: list[Memory] = []
        if not self.no_report:
            report_memories = self._report_memories()
            memories.extend(report_memories)
            self.last_stats["reports"] = len(report_memories)
        if not self.no_nodes:
            node_memories = self._node_memories()
            memories.extend(node_memories)
            self.last_stats["nodes"] = len(node_memories)

        if self.dry_run:
            return len(memories)
        if not memories:
            return 0

        vectors = embed_batch([f"{m.summary}\n{m.raw_text}" for m in memories])
        return self.store.add_batch(memories, vectors)

    def serializable_stats(self) -> dict:
        return {**self.last_stats, "skipped": dict(self.last_stats.get("skipped", {}))}

    def _validate_inputs(self) -> None:
        missing: list[str] = []
        if not self.no_report and not self.report_path.exists():
            missing.append(str(self.report_path))
        if not self.no_nodes and not self.graph_path.exists():
            missing.append(str(self.graph_path))
        if missing:
            missing_names = ", ".join(path.name for path in map(Path, missing))
            raise GraphifyOutputMissingError(
                f"Missing Graphify output under graphify-out: {missing_names}. "
                f"Expected files: {self.report_path} and {self.graph_path}"
            )

    def _report_memories(self) -> list[Memory]:
        text = self.report_path.read_text(errors="ignore")
        sections = _split_report_sections(text)
        timestamp = _mtime(self.report_path)
        memories = []
        for heading, body in sections:
            raw_text = f"## {heading}\n\n{body}".strip()
            memories.append(
                Memory(
                    id=_deterministic_report_id(self.repo, heading, self.report_path),
                    type="graphify_report",
                    summary=f"Graphify report: {heading}",
                    raw_text=self._redact(raw_text),
                    source=str(self.report_path),
                    repo=self.repo,
                    timestamp=timestamp,
                    tags=["graphify", "code_graph", "architecture"],
                    importance=_report_importance(heading, body),
                )
            )
        return memories

    def _node_memories(self) -> list[Memory]:
        try:
            graph = json.loads(self.graph_path.read_text(errors="ignore"))
        except json.JSONDecodeError as exc:
            self.last_stats["errors"] += 1
            raise ValueError(f"Invalid Graphify graph.json: {exc}") from exc

        nodes = graph.get("nodes") or []
        if not isinstance(nodes, list):
            raise ValueError("Invalid Graphify graph.json: 'nodes' must be a list")

        edges = _graph_edges(graph)
        degree_by_id = _degrees(edges)
        neighbors_by_id = _neighbors(edges)
        timestamp = _mtime(self.graph_path)
        memories: list[Memory] = []

        for node in nodes:
            if not isinstance(node, dict):
                self.last_stats["skipped"]["invalid_node"] += 1
                continue
            node_id = str(node.get("id") or node.get("key") or node.get("label") or "").strip()
            if not node_id:
                self.last_stats["skipped"]["missing_node_id"] += 1
                continue
            degree = degree_by_id.get(node_id, 0)
            if degree < self.min_degree:
                self.last_stats["skipped"]["min_degree"] += 1
                continue
            memories.append(self._memory_for_node(node, node_id, degree, neighbors_by_id.get(node_id, []), timestamp))
        return memories

    def _memory_for_node(self, node: dict[str, Any], node_id: str, degree: int, neighbors: list[str], timestamp: datetime) -> Memory:
        label = str(node.get("label") or node.get("name") or node_id)
        node_type = str(node.get("type") or node.get("kind") or "unknown")
        source_file = str(node.get("file") or node.get("path") or node.get("source_file") or "")
        community = str(node.get("community") or node.get("community_id") or "")
        raw_lines = [
            f"Label: {label}",
            f"Type: {node_type}",
            f"Graphify node ID: {node_id}",
            f"Source file: {source_file or 'unknown'}",
            f"Community: {community or 'unknown'}",
            f"Degree: {degree}",
            f"Neighbors: {', '.join(sorted(neighbors)) if neighbors else 'none'}",
        ]
        if node.get("summary"):
            raw_lines.append(f"Summary: {node['summary']}")

        tags = ["graphify", "code_graph", f"node_type:{node_type}"]
        if community:
            tags.append(f"community:{community}")
        if source_file:
            tags.append(f"source_file:{source_file}")

        return Memory(
            id=_deterministic_node_id(self.repo, node_id),
            type="graphify_node",
            summary=f"Graphify node: {label} ({node_type})",
            raw_text=self._redact("\n".join(raw_lines)),
            source=str(self.graph_path),
            repo=self.repo,
            timestamp=timestamp,
            tags=tags,
            importance=_node_importance(degree, source_file),
        )


def _infer_repo(path: Path) -> str:
    current = path.resolve()
    if current.is_file():
        current = current.parent
    if current.name == "graphify-out":
        return current.parent.name
    return current.name


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)


def _split_report_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_heading is not None:
                sections.append((current_heading, current_lines))
            current_heading = line[3:].strip() or "Untitled"
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)

    if current_heading is not None:
        sections.append((current_heading, current_lines))

    return [(heading, "\n".join(lines).strip()) for heading, lines in sections if "\n".join(lines).strip()]


def _graph_edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    raw_edges = graph.get("links")
    if raw_edges is None:
        raw_edges = graph.get("edges")
    if not isinstance(raw_edges, list):
        return []
    return [edge for edge in raw_edges if isinstance(edge, dict)]


def _endpoint_id(endpoint: Any) -> str:
    if isinstance(endpoint, dict):
        return str(endpoint.get("id") or endpoint.get("key") or endpoint.get("label") or "")
    return str(endpoint)


def _degrees(edges: list[dict[str, Any]]) -> Counter:
    counts: Counter = Counter()
    for edge in edges:
        source = _endpoint_id(edge.get("source"))
        target = _endpoint_id(edge.get("target"))
        if source:
            counts[source] += 1
        if target:
            counts[target] += 1
    return counts


def _neighbors(edges: list[dict[str, Any]]) -> dict[str, list[str]]:
    neighbors: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        source = _endpoint_id(edge.get("source"))
        target = _endpoint_id(edge.get("target"))
        if source and target:
            neighbors[source].add(target)
            neighbors[target].add(source)
    return {key: sorted(value) for key, value in neighbors.items()}


def _report_importance(heading: str, body: str) -> float:
    text = f"{heading} {body}".lower()
    if any(term in text for term in ["architecture", "overview", "god node", "critical"]):
        return 0.85
    return 0.70


def _node_importance(degree: int, source_file: str) -> float:
    if degree >= 5:
        return 0.90
    if source_file and degree >= 2:
        return 0.75
    if source_file or degree > 0:
        return 0.60
    return 0.40
