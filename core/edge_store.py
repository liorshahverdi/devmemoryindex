"""
Memory Entanglement — Typed Edge Graph (T2-A)

Stores directed, typed edges between memories in a separate LanceDB table.
Edge types encode causal / semantic relationships:
  caused_by   — this memory was caused by another (e.g. a bug caused a failure note)
  fixed_by    — this memory was fixed by another (e.g. a failure note fixed by a commit)
  references  — this memory references another
  supersedes  — this memory replaces another (use with forget on old memory)
  contradicts — this memory contradicts another
  related_to  — loose semantic relationship

Usage:
    store = EdgeStore()
    store.add_edge(from_id, to_id, "fixed_by")
    graph = store.get_graph(memory_id, depth=2)
    chain = store.trace_causality(memory_id)
"""

from __future__ import annotations

import threading
from datetime import datetime

import lancedb
import pyarrow as pa

VALID_EDGE_TYPES = {
    "caused_by",
    "fixed_by",
    "references",
    "supersedes",
    "contradicts",
    "related_to",
}

_edge_schema = pa.schema([
    pa.field("from_id", pa.string()),
    pa.field("to_id", pa.string()),
    pa.field("edge_type", pa.string()),
    pa.field("confidence", pa.float64()),
    pa.field("created_at", pa.timestamp("us")),
    pa.field("source", pa.string()),   # "agent" | "auto" | "llm_inference"
])


class EdgeStore:
    def __init__(self, db_path: str = "./memory_db"):
        self.db = lancedb.connect(db_path)
        self._table = self._init_table()
        self._lock = threading.Lock()

    def _init_table(self):
        if "edges" in self.db.table_names():
            table = self.db.open_table("edges")
            try:
                table.search().limit(1).to_list()
            except Exception:
                self.db.drop_table("edges")
                return self.db.create_table("edges", schema=_edge_schema)
            return table
        return self.db.create_table("edges", schema=_edge_schema)

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
        confidence: float = 1.0,
        source: str = "agent",
    ) -> bool:
        """Add a directed edge from_id → to_id of the given type.

        Returns False if the edge already exists (same from/to/type triple).
        """
        if edge_type not in VALID_EDGE_TYPES:
            raise ValueError(f"Unknown edge type '{edge_type}'. Valid: {sorted(VALID_EDGE_TYPES)}")
        if self._edge_exists(from_id, to_id, edge_type):
            return False
        record = {
            "from_id": from_id,
            "to_id": to_id,
            "edge_type": edge_type,
            "confidence": float(confidence),
            "created_at": datetime.utcnow(),
            "source": source,
        }
        with self._lock:
            batch = pa.Table.from_pylist([record], schema=_edge_schema)
            self._table.add(batch)
        return True

    def _edge_exists(self, from_id: str, to_id: str, edge_type: str) -> bool:
        safe_from = from_id.replace("'", "''")
        safe_to = to_id.replace("'", "''")
        safe_type = edge_type.replace("'", "''")
        try:
            results = (
                self._table
                .search()
                .where(
                    f"from_id = '{safe_from}' AND to_id = '{safe_to}' AND edge_type = '{safe_type}'"
                )
                .limit(1)
                .to_list()
            )
            return len(results) > 0
        except Exception:
            return False

    def get_edges(self, memory_id: str) -> list[dict]:
        """Return all edges where memory_id is from_id or to_id."""
        safe_id = memory_id.replace("'", "''")
        try:
            results = (
                self._table
                .search()
                .where(f"from_id = '{safe_id}' OR to_id = '{safe_id}'")
                .limit(1000)
                .to_list()
            )
            return [self._clean_edge(r) for r in results]
        except Exception:
            return []

    def get_graph(self, memory_id: str, depth: int = 2) -> dict:
        """Return the subgraph up to `depth` hops from memory_id.

        Returns:
            {
                "root": memory_id,
                "nodes": [memory_id, ...],   # all reachable memory IDs
                "edges": [{from_id, to_id, edge_type, confidence}, ...]
            }
        """
        visited_nodes: set[str] = set()
        all_edges: list[dict] = []
        frontier = {memory_id}

        for _ in range(depth):
            if not frontier:
                break
            next_frontier: set[str] = set()
            for node_id in frontier:
                if node_id in visited_nodes:
                    continue
                visited_nodes.add(node_id)
                edges = self.get_edges(node_id)
                for e in edges:
                    # Avoid duplicate edges
                    edge_key = (e["from_id"], e["to_id"], e["edge_type"])
                    if not any(
                        (x["from_id"], x["to_id"], x["edge_type"]) == edge_key
                        for x in all_edges
                    ):
                        all_edges.append(e)
                    neighbor = e["to_id"] if e["from_id"] == node_id else e["from_id"]
                    if neighbor not in visited_nodes:
                        next_frontier.add(neighbor)
            frontier = next_frontier

        return {
            "root": memory_id,
            "nodes": list(visited_nodes),
            "edges": all_edges,
        }

    def trace_causality(self, memory_id: str) -> list[dict]:
        """Follow the causal chain (caused_by edges) from memory_id to root cause.

        Returns an ordered list of {memory_id, edge_type} from the given memory
        back to the root cause. Stops at depth 10 to prevent cycles.

        Returns:
            [{"memory_id": id, "step": N, "via_edge": edge_type}, ...]
        """
        chain = [{"memory_id": memory_id, "step": 0, "via_edge": None}]
        visited = {memory_id}
        current = memory_id

        for step in range(1, 11):
            # Look for caused_by edges going outward from current
            safe_id = current.replace("'", "''")
            try:
                edges = (
                    self._table
                    .search()
                    .where(
                        f"from_id = '{safe_id}' AND "
                        f"(edge_type = 'caused_by' OR edge_type = 'fixed_by')"
                    )
                    .limit(1)
                    .to_list()
                )
            except Exception:
                break

            if not edges:
                break

            next_id = edges[0]["to_id"]
            edge_type = edges[0]["edge_type"]

            if next_id in visited:
                break  # cycle guard

            visited.add(next_id)
            chain.append({"memory_id": next_id, "step": step, "via_edge": edge_type})
            current = next_id

        return chain

    def delete_edges_for(self, memory_id: str) -> int:
        """Remove all edges connected to memory_id. Called when a memory is deleted."""
        safe_id = memory_id.replace("'", "''")
        try:
            before = self._table.count_rows()
            with self._lock:
                self._table.delete(f"from_id = '{safe_id}' OR to_id = '{safe_id}'")
            after = self._table.count_rows()
            return before - after
        except Exception:
            return 0

    def get_all_edges(self) -> list[dict]:
        try:
            return [self._clean_edge(r) for r in self._table.to_arrow().to_pylist()]
        except Exception:
            return []

    @staticmethod
    def _clean_edge(r: dict) -> dict:
        return {
            "from_id": r.get("from_id"),
            "to_id": r.get("to_id"),
            "edge_type": r.get("edge_type"),
            "confidence": r.get("confidence", 1.0),
            "source": r.get("source", "agent"),
            "created_at": str(r.get("created_at", "")),
        }
