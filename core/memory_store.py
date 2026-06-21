import threading

import lancedb
import pyarrow as pa
from core.schema import Memory
from core.ranking import compute_score, compute_score_breakdown, recency_score
from core.context_cache import cache as _context_cache

VECTOR_DIM = 384
_schema = pa.schema([
    pa.field("id", pa.string()),
    pa.field("type", pa.string()),
    pa.field("summary", pa.string()),
    pa.field("raw_text", pa.string()),
    pa.field("source", pa.string()),
    pa.field("repo", pa.string()),
    pa.field("timestamp", pa.timestamp("us")),
    pa.field("tags", pa.list_(pa.string())),
    pa.field("importance", pa.float64()),
    pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
    pa.field("times_retrieved", pa.int64()),
    pa.field("times_accessed", pa.int64()),
    pa.field("status", pa.string()),
    pa.field("deprecation_reason", pa.string()),
])

_STOPWORDS = {
    "a", "an", "the", "is", "in", "on", "at", "to", "for", "of", "and",
    "or", "where", "what", "how", "why", "when", "i", "me", "my", "it",
    "this", "that", "with", "from", "by", "be", "was", "are", "do", "did",
    "does", "not", "no", "can", "could", "would", "should", "have", "has",
    "had", "are", "there", "any", "which", "who", "its", "as", "if",
}


def _keyword_where(query: str) -> str:
    """Build a keyword WHERE clause from individual meaningful query terms.

    Splits the query into words, drops stopwords and short tokens, and returns
    a SQL OR chain matching summary or raw_text for each term (capped at 6).
    Falls back to a full-phrase match for very short queries (one meaningful term).
    """
    import re
    words = re.findall(r"\w+", query.lower())
    terms = [w for w in words if w not in _STOPWORDS and len(w) >= 3]

    if not terms:
        safe = query.lower().replace("'", "''")
        return f"LOWER(summary) LIKE '%{safe}%' OR LOWER(raw_text) LIKE '%{safe}%'"

    # Deduplicate while preserving order, cap to avoid huge WHERE clauses.
    seen: set[str] = set()
    unique_terms: list[str] = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            unique_terms.append(t)
    unique_terms = unique_terms[:6]

    parts = []
    for term in unique_terms:
        safe = term.replace("'", "''")  # terms are already lowercased
        parts.append(f"LOWER(summary) LIKE '%{safe}%' OR LOWER(raw_text) LIKE '%{safe}%'")
    return " OR ".join(parts)


class MemoryStore:
    def __init__(self, db_path="./memory_db"):
        self.db_path = db_path
        self.db = lancedb.connect(db_path)
        self.collection = self._init_table()
        self._write_lock = threading.Lock()  # serializes all writes; LanceDB is not thread-safe for concurrent writes
        self._write_count = 0
        self._backup_every = 100  # auto-backup after every N successful writes

    @staticmethod
    def _try_salvage(table, backup_path) -> int:
        """Dump readable records from a (potentially corrupt) table to JSON.

        Called before wiping a corrupt table so no data is silently lost.
        Returns the number of records saved, or 0 on failure.
        """
        import json
        from pathlib import Path as _Path
        try:
            try:
                records = table.to_arrow().to_pylist()
            except Exception:
                records = table.search().limit(10000).to_list()
        except Exception:
            return 0
        if not records:
            return 0
        serializable = []
        for r in records:
            rec = {k: v for k, v in r.items() if k != "vector"}
            ts = rec.get("timestamp")
            if hasattr(ts, "isoformat"):
                rec["timestamp"] = ts.isoformat()
            serializable.append(rec)
        try:
            p = _Path(backup_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(serializable, indent=2, default=str))
            return len(serializable)
        except Exception:
            return 0

    def _periodic_backup(self) -> None:
        """Auto-export all memories to a rolling JSON backup.

        Called after every _backup_every writes. Writes to
        ~/.config/devmemory/backups/memories_latest.json.
        Best-effort — never raises.
        """
        import json
        from pathlib import Path as _Path
        backup_dir = _Path.home() / ".config" / "devmemory" / "backups"
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            records = self.get_all()
            if not records:
                return
            serializable = []
            for r in records:
                rec = {k: v for k, v in r.items() if k != "vector"}
                ts = rec.get("timestamp")
                if hasattr(ts, "isoformat"):
                    rec["timestamp"] = ts.isoformat()
                serializable.append(rec)
            (backup_dir / "memories_latest.json").write_text(
                json.dumps(serializable, indent=2, default=str)
            )
        except Exception:
            pass  # Never crash the main write path

    def _wipe_and_recreate(self) -> "lancedb.Table":
        """Physically remove the corrupt .lance directory and recreate the table.

        Uses shutil.rmtree rather than db.drop_table() to avoid a LanceDB
        manifest-version overflow bug: each drop_table() call increments the
        manifest version counter by a large delta, and after several cycles the
        counter wraps around near UINT64_MAX, causing all subsequent operations
        to fail. rmtree avoids this entirely by starting fresh on disk.
        """
        import shutil
        from pathlib import Path as _Path
        lance_dir = _Path(self.db_path) / "memories.lance"
        if lance_dir.exists():
            shutil.rmtree(lance_dir)
        # Reconnect so lancedb picks up the clean state
        self.db = lancedb.connect(self.db_path)
        return self.db.create_table("memories", schema=_schema)

    def _init_table(self):
        # Open existing table without schema re-validation to allow migrations.
        # Create with full schema only for brand-new stores.
        if "memories" in self.db.table_names():
            table = self.db.open_table("memories")
        else:
            return self.db.create_table("memories", schema=_schema)

        # Verify the table is scannable. Corrupt tables (missing fragments from
        # partial deletes or LanceDB manifest overflow) must be recreated.
        try:
            table.search().limit(1).to_list()
        except Exception:
            import warnings
            from pathlib import Path as _Path
            # Try to salvage readable data before wiping
            backup_path = _Path.home() / ".config" / "devmemory" / "backups" / "memories_latest.json"
            salvaged = self._try_salvage(table, backup_path)
            msg = (
                f"[memory_store] Table 'memories' is corrupt — wiping and recreating. "
                + (f"Auto-saved {salvaged} memories to {backup_path}. "
                   f"Run 'devmemory import {backup_path}' to restore."
                   if salvaged
                   else "No memories could be salvaged (table unreadable).")
            )
            warnings.warn(msg, RuntimeWarning, stacklevel=2)
            return self._wipe_and_recreate()

        # Schema migration: add columns for stores created before various features.
        existing = {f.name for f in table.schema}
        missing = {}
        if "times_retrieved" not in existing:
            missing["times_retrieved"] = "cast(0 as bigint)"
        if "times_accessed" not in existing:
            missing["times_accessed"] = "cast(0 as bigint)"
        if "status" not in existing:
            missing["status"] = "'active'"
        if "deprecation_reason" not in existing:
            missing["deprecation_reason"] = "''"
        if missing:
            table.add_columns(missing)  # raises clearly if it fails

        return table
    
    def add(self, memory: Memory, vector: list) -> bool:
        """Insert a memory. Returns False (no-op) if the id already exists."""
        if self.exists(memory.id):
            return False
        with self._write_lock:
            batch = pa.Table.from_pylist([self._to_record(memory, vector)], schema=_schema)
            self.collection.add(batch)
        _context_cache.invalidate()  # new memory may change context results
        self._write_count += 1
        if self._write_count % self._backup_every == 0:
            self._periodic_backup()
        return True

    def add_batch(self, memories: list[Memory], vectors: list[list]) -> int:
        """Insert multiple memories in a single DB write. Returns count added.

        Performs one batch exists-check and one collection.add() call, which is
        dramatically faster than calling add() N times (avoids N separate Lance
        fragment writes). Duplicates are silently skipped.
        """
        if not memories:
            return 0
        ids = [m.id for m in memories]
        existing = self._batch_existing_ids(ids)
        records = [
            self._to_record(m, v)
            for m, v in zip(memories, vectors)
            if m.id not in existing
        ]
        if not records:
            return 0
        with self._write_lock:
            batch = pa.Table.from_pylist(records, schema=_schema)
            self.collection.add(batch)
        _context_cache.invalidate()
        self._write_count += len(records)
        if self._write_count % self._backup_every < len(records):
            self._periodic_backup()
        return len(records)

    @staticmethod
    def _normalize_timestamp(ts) -> "datetime":
        """Coerce timestamp to a datetime object for PyArrow compatibility.

        Memory.timestamp is typed as datetime, but some callers pass an ISO
        string (e.g. test fixtures using datetime.now().isoformat()). PyArrow's
        from_pylist with an explicit pa.timestamp("us") schema cannot convert
        ISO strings — it expects a Python datetime or int microseconds.
        """
        from datetime import datetime as _dt
        if isinstance(ts, _dt):
            return ts
        if isinstance(ts, str):
            try:
                return _dt.fromisoformat(ts)
            except Exception:
                return _dt.utcnow()
        # Numeric (unix timestamp in seconds or ms) — best-effort
        try:
            return _dt.utcfromtimestamp(float(ts))
        except Exception:
            return _dt.utcnow()

    def _to_record(self, memory: Memory, vector: list) -> dict:
        return {
            "id": memory.id,
            "type": memory.type,
            "summary": memory.summary,
            "raw_text": memory.raw_text,
            "source": memory.source,
            "repo": memory.repo,
            "timestamp": self._normalize_timestamp(memory.timestamp),
            "tags": memory.tags,
            "importance": memory.importance,
            "vector": vector,
            "times_retrieved": 0,
            "times_accessed": 0,
            "status": getattr(memory, "status", "active"),
            "deprecation_reason": getattr(memory, "deprecation_reason", ""),
        }

    def _batch_existing_ids(self, ids: list[str]) -> set[str]:
        """Return the subset of ids already in the store (single WHERE IN query)."""
        if not ids:
            return set()
        try:
            escaped = "', '".join(i.replace("'", "''") for i in ids)
            results = (
                self.collection
                .search()
                .where(f"id IN ('{escaped}')")
                .limit(len(ids))
                .to_list()
            )
            return {r["id"] for r in results}
        except Exception:
            return set()

    def exists(self, memory_id: str) -> bool:
        safe_id = memory_id.replace("'", "''")
        try:
            results = (
                self.collection
                .search()
                .where(f"id = '{safe_id}'")
                .limit(1)
                .to_list()
            )
            return len(results) > 0
        except Exception:
            return False

    def _increment_counter(self, memory_id: str, column: str) -> None:
        """Increment times_retrieved or times_accessed by 1. Best-effort, never raises."""
        try:
            safe_id = memory_id.replace("'", "''")
            results = (
                self.collection
                .search()
                .where(f"id = '{safe_id}'")
                .limit(1)
                .to_list()
            )
            if not results:
                return
            new_val = (results[0].get(column) or 0) + 1
            with self._write_lock:
                self.collection.update(
                    where=f"id = '{safe_id}'",
                    values={column: new_val},
                )
        except Exception:
            pass

    def reinforce(self, memory_id: str, boost: float = 0.05) -> None:
        """Passively boost importance of a retrieved memory, capped at 0.8.

        Called automatically after search hits and get_by_id(). Not intended
        for explicit agent feedback — use boost_importance() for that (cap 0.95).
        """
        safe_id = memory_id.replace("'", "''")
        try:
            results = (
                self.collection
                .search()
                .where(f"id = '{safe_id}'")
                .limit(1)
                .to_list()
            )
            if not results:
                return
            new_importance = min(0.8, results[0].get("importance", 0.5) + boost)
            with self._write_lock:
                self.collection.update(
                    where=f"id = '{safe_id}'",
                    values={"importance": new_importance},
                )
        except Exception:
            pass  # Non-critical

    def semantic_search(self, vector: list, k: int = 5) -> list:
        return self.collection.search(vector).limit(k).to_list()

    def _reinit_after_corrupt(self) -> None:
        """Re-initialize the table after a mid-session fragment error.

        Called when hybrid_search (or another op) encounters a LanceDB error
        after startup — i.e. a fragment file was removed while the process was
        running. Wipes and recreates the table so subsequent calls succeed
        (returning empty results) rather than continuing to crash.
        """
        import warnings
        from pathlib import Path as _Path
        backup_path = _Path.home() / ".config" / "devmemory" / "backups" / "memories_latest.json"
        # Best-effort salvage — table may be completely unreadable at this point
        try:
            salvaged = self._try_salvage(self.collection, backup_path)
        except Exception:
            salvaged = 0
        msg = (
            "[memory_store] Mid-session corruption detected — reinitializing table. "
            + (f"Auto-saved {salvaged} memories to {backup_path}."
               if salvaged else "No memories could be salvaged.")
        )
        warnings.warn(msg, RuntimeWarning, stacklevel=3)
        self.collection = self._wipe_and_recreate()

    def text_search(
        self,
        query: str,
        k: int = 5,
        type_filter: str | None = None,
        repo_filter: str | None = None,
        speaker_filter: str | None = None,
    ) -> list:
        """Fast keyword-only search that avoids embedding model startup.

        Intended for interactive CLI fast paths. It trades some semantic recall
        for predictable latency by searching summary/raw_text with meaningful
        query terms and ranking by term coverage, repo/type filters, importance,
        and recency.
        """
        conditions: list[str] = ["(status = 'active' OR status IS NULL)"]
        if type_filter:
            safe_type = type_filter.replace("'", "''")
            conditions.append(f"type LIKE '{safe_type}%'")
        if repo_filter:
            safe_repo = repo_filter.replace("'", "''")
            conditions.append(f"repo = '{safe_repo}'")
        where_clause = " AND ".join(conditions)
        kw_where = f"({_keyword_where(query)}) AND {where_clause}"
        try:
            limit = min(max(k * 10, 50), 200)
            results = self.collection.search().where(kw_where).limit(limit).to_list()
        except Exception:
            return []

        if speaker_filter:
            tag_to_find = f"speaker:{speaker_filter.lower()}"
            results = [r for r in results if tag_to_find in (r.get("tags") or [])]

        import re as _re
        terms = [
            w for w in _re.findall(r"\w+", query.lower())
            if w not in _STOPWORDS and len(w) >= 3
        ][:6]

        def _coverage_score(memory: dict) -> tuple:
            summary = (memory.get("summary") or "").lower()
            raw = (memory.get("raw_text") or "").lower()
            term_score = 0
            for term in terms:
                if term in summary:
                    term_score += 2
                elif term in raw:
                    term_score += 1
            return (
                term_score,
                memory.get("importance") or 0,
                recency_score(memory.get("timestamp")),
            )

        scored = [(r, _coverage_score(r)) for r in results]
        min_terms = 2 if len(terms) >= 3 else 1
        scored = [item for item in scored if item[1][0] >= min_terms]
        return [r for r, _score in sorted(scored, key=lambda item: item[1], reverse=True)[:k]]

    def hybrid_search(
        self,
        query: str,
        vector: list,
        k: int = 5,
        type_filter: str | None = None,
        repo_filter: str | None = None,
        speaker_filter: str | None = None,
        update_counters: bool = False,
    ) -> list:
        try:
            return self._hybrid_search_impl(
                query, vector, k, type_filter, repo_filter, speaker_filter, update_counters=update_counters
            )
        except Exception as exc:
            err = str(exc).lower()
            if "lance" in err or "not found" in err or "fragment" in err:
                self._reinit_after_corrupt()
                return []
            raise

    def _hybrid_search_impl(
        self,
        query: str,
        vector: list,
        k: int = 5,
        type_filter: str | None = None,
        repo_filter: str | None = None,
        speaker_filter: str | None = None,
        update_counters: bool = False,
    ) -> list:
        # Build optional WHERE clause applied at the DB level so filters
        # don't silently exclude results after the k-cap is already applied.
        conditions: list[str] = []
        if type_filter:
            safe_type = type_filter.replace("'", "''")
            # Use prefix match so "meeting" finds "meeting_transcript",
            # "copilot" finds "copilot_chat", etc.
            conditions.append(f"type LIKE '{safe_type}%'")
        if repo_filter:
            safe_repo = repo_filter.replace("'", "''")
            conditions.append(f"repo = '{safe_repo}'")
        where_clause = " AND ".join(conditions) if conditions else None

        # Always exclude deprecated memories from active searches.
        # Use parentheses so this OR expression doesn't interfere with AND-joined filters.
        active_clause = "(status = 'active' OR status IS NULL)"
        if conditions:
            conditions.insert(0, active_clause)
        else:
            conditions = [active_clause]
        where_clause = " AND ".join(conditions)

        # 1. Semantic search — over-retrieve
        sem_q = self.collection.search(vector).limit(50)
        if where_clause:
            sem_q = sem_q.where(where_clause)
        semantic_results = sem_q.to_list()

        # 2. Keyword search — catch exact term matches semantic may miss.
        # Use individual meaningful terms rather than the full query string so
        # natural-language questions ("where is buffer playback in the code")
        # still match memories containing "buffer" or "playback".
        kw_where = _keyword_where(query)
        if where_clause:
            kw_where = f"({kw_where}) AND {where_clause}"
        try:
            keyword_results = (
                self.collection
                .search()
                .where(kw_where)
                .limit(50)
                .to_list()
            )
        except Exception:
            keyword_results = []

        # 3. Merge and deduplicate by id
        # Semantic results carry _distance from vector search.
        # Keyword hits get a synthetic distance based on term-match ratio:
        # a memory matching all query terms gets distance=0.0 (perfect),
        # one matching only 1 of 3 terms gets distance=0.67.
        # This prevents the common failure where a generic term like "connector"
        # causes many loosely-related memories to tie at distance=0.0 and then
        # sort purely by recency, burying the specific commit that matches all terms.
        import re as _re
        _query_terms = [
            w for w in _re.findall(r"\w+", query.lower())
            if w not in _STOPWORDS and len(w) >= 3
        ][:6]

        def _term_match_distance(memory: dict) -> float:
            if not _query_terms:
                return 0.0
            summary_text = (memory.get("summary") or "").lower()
            raw_text = (memory.get("raw_text") or "").lower()
            # Summary hits count 2×: a term in the summary is a primary signal
            # (definition, filename) vs a secondary signal (import, passing reference).
            # This lets definition files outrank files that merely import the same class.
            score = 0
            for t in _query_terms:
                if t in summary_text:
                    score += 2
                elif t in raw_text:
                    score += 1
            max_score = len(_query_terms) * 2
            return max(0.0, 1.0 - score / max_score)

        keyword_ids = {r["id"] for r in keyword_results}
        combined = {r["id"]: r for r in semantic_results}
        for r in keyword_results:
            if r["id"] not in combined:
                combined[r["id"]] = r

        # Speaker filter: applied after merge, before scoring.
        # Matches memories with the tag "speaker:<speaker_filter_lowercase>".
        if speaker_filter:
            tag_to_find = f"speaker:{speaker_filter.lower()}"
            combined = {
                k: v for k, v in combined.items()
                if tag_to_find in (v.get("tags") or [])
            }

        for r in combined.values():
            if r["id"] in keyword_ids:
                kw_dist = _term_match_distance(r)
                # Only override if keyword match gives a better (lower) distance
                # than the semantic result's own distance.
                if kw_dist < r.get("_distance", 1.0):
                    r["_distance"] = kw_dist

        # 4. Score and rank — attach full breakdown for explainability (T1-A)
        scored = list(combined.values())
        for r in scored:
            breakdown = compute_score_breakdown(r)
            r["_score"] = breakdown["final"]
            r["score_breakdown"] = breakdown

        # Deprioritize failure_note results unless the query signals negative intent.
        _NEGATIVE_KEYWORDS = {
            "avoid", "failed", "broken", "didn't work", "not work",
            "mistake", "wrong", "don't", "shouldn't", "error", "bug",
        }
        query_lower = query.lower()
        negative_intent = any(kw in query_lower for kw in _NEGATIVE_KEYWORDS)
        if not negative_intent:
            for r in scored:
                if r.get("type") == "failure_note":
                    r["_score"] *= 0.4

        # CTR dampening (I4): memories retrieved often but rarely accessed are likely
        # low-signal. Apply a soft penalty when click-through rate < 10% with enough
        # data (>= 5 retrievals) to avoid penalising brand-new memories.
        for r in scored:
            retrieved = r.get("times_retrieved", 0) or 0
            accessed = r.get("times_accessed", 0) or 0
            if retrieved >= 5 and (accessed / retrieved) < 0.1:
                r["_score"] *= 0.8

        ranked = sorted(scored, key=lambda r: r["_score"], reverse=True)

        top = ranked[:k]

        # 5. Attach related memory IDs — nearest neighbours from the semantic
        #    pool that didn't make it into top-k. No extra search calls needed.
        top_ids = {r["id"] for r in top}
        related_pool = [r for r in semantic_results if r["id"] not in top_ids]
        for r in top:
            r["related"] = [n["id"] for n in related_pool[:3]]

        # 6. Optionally increment times_retrieved for all top results.
        # This is disabled by default because LanceDB updates are expensive on
        # the interactive read path; daemons or batch jobs can opt in.
        if update_counters:
            for r in top:
                self._increment_counter(r["id"], "times_retrieved")

        return top

    def _resolve_id(self, memory_id: str) -> str | None:
        """Resolve an exact ID or a unique short prefix to the canonical full ID."""
        safe_id = memory_id.replace("'", "''")
        try:
            exact = (
                self.collection
                .search()
                .where(f"id = '{safe_id}'")
                .limit(1)
                .to_list()
            )
            if exact:
                return exact[0]["id"]

            # Search output displays 8-character prefixes; accept any unique
            # prefix users copy from that table, but refuse ambiguous prefixes.
            if len(memory_id) >= 8:
                prefix_results = (
                    self.collection
                    .search()
                    .where(f"id LIKE '{safe_id}%'")
                    .limit(2)
                    .to_list()
                )
                if len(prefix_results) == 1:
                    return prefix_results[0]["id"]
        except Exception:
            return None
        return None

    def get_by_id(self, memory_id: str, reinforce: bool = True) -> dict | None:
        """Fetch a single memory by exact ID or unique short prefix.

        Reinforces importance by a small amount when reinforce=True (default) —
        an explicit fetch is a strong signal that this memory is useful.
        Returns None if not found or if a prefix matches multiple memories.
        """
        resolved_id = self._resolve_id(memory_id)
        if resolved_id is None:
            return None
        safe_id = resolved_id.replace("'", "''")
        try:
            results = (
                self.collection
                .search()
                .where(f"id = '{safe_id}'")
                .limit(1)
                .to_list()
            )
            if not results:
                return None
            if reinforce:
                self.reinforce(resolved_id, boost=0.02)
                self._increment_counter(resolved_id, "times_accessed")
            return results[0]
        except Exception:
            return None

    def update(
        self,
        memory_id: str,
        summary: str | None = None,
        raw_text: str | None = None,
        importance: float | None = None,
    ) -> bool:
        """Update an existing memory's fields in-place.

        Re-embeds and replaces the vector when summary or raw_text changes
        (requires delete + re-add). Preserves times_retrieved and times_accessed.
        Returns False if memory_id is not found.
        """
        record = self.get_by_id(memory_id, reinforce=False)
        if record is None:
            return False

        new_summary = (summary.strip()[:200] if summary else record.get("summary", ""))
        new_raw = raw_text if raw_text is not None else record.get("raw_text", "")
        new_importance = importance if importance is not None else record.get("importance", 0.5)
        text_changed = summary is not None or raw_text is not None

        if text_changed:
            from core.embeddings import embed
            new_vector = embed(new_summary)
            self.delete(memory_id)
            with self._write_lock:
                batch = pa.Table.from_pylist([{
                    "id": memory_id,
                    "type": record.get("type", "agent_solution"),
                    "summary": new_summary,
                    "raw_text": new_raw,
                    "source": record.get("source", "mcp_agent"),
                    "repo": record.get("repo"),
                    "timestamp": record.get("timestamp"),
                    "tags": record.get("tags", []),
                    "importance": new_importance,
                    "vector": new_vector,
                    "times_retrieved": record.get("times_retrieved", 0) or 0,
                    "times_accessed": record.get("times_accessed", 0) or 0,
                    "status": record.get("status", "active") or "active",
                    "deprecation_reason": record.get("deprecation_reason", "") or "",
                }], schema=_schema)
                self.collection.add(batch)
        else:
            with self._write_lock:
                self.collection.update(
                    where=f"id = '{memory_id}'",
                    values={"importance": new_importance},
                )

        _context_cache.invalidate()
        return True

    def boost_importance(self, memory_id: str, amount: float = 0.05, cap: float = 0.95) -> float | None:
        """Explicitly boost importance by amount up to cap.

        Returns new importance value, or None if memory_id is not found.
        """
        try:
            safe_id = memory_id.replace("'", "''")
            results = (
                self.collection
                .search()
                .where(f"id = '{safe_id}'")
                .limit(1)
                .to_list()
            )
            if not results:
                return None
            new_val = min(cap, (results[0].get("importance") or 0.5) + amount)
            with self._write_lock:
                self.collection.update(
                    where=f"id = '{safe_id}'",
                    values={"importance": new_val},
                )
            return new_val
        except Exception:
            return None

    def delete(self, memory_id: str):
        safe_id = memory_id.replace("'", "''")
        with self._write_lock:
            self.collection.delete(f"id = '{safe_id}'")

    def get_ids_by_source(self, source: str, type_filter: str | None = None) -> set[str]:
        """Return the set of memory IDs stored for a given source path.

        Used by connectors to detect stale chunks: after re-indexing a file,
        any ID in this set that wasn't produced by the current content is stale
        and should be deleted.
        """
        safe_source = source.replace("'", "''")
        where = f"source = '{safe_source}'"
        if type_filter:
            safe_type = type_filter.replace("'", "''")
            where += f" AND type = '{safe_type}'"
        try:
            results = (
                self.collection
                .search()
                .where(where)
                .limit(10000)
                .to_list()
            )
            return {r["id"] for r in results}
        except Exception:
            return set()

    def summary_quality(self) -> dict:
        """Return summary length distribution and IDs of short-summary memories.

        A summary under 20 characters is flagged as low-quality — too short to
        reliably match future search queries.
        """
        records = self.get_all()
        lengths = [len(r.get("summary") or "") for r in records]
        short = [
            {"id": r["id"][:8], "summary": r.get("summary", ""), "type": r.get("type", "")}
            for r in records
            if len(r.get("summary") or "") < 20
        ]
        buckets = {"<20": 0, "20-50": 0, "51-100": 0, "101-200": 0, ">200": 0}
        for l in lengths:
            if l < 20:
                buckets["<20"] += 1
            elif l <= 50:
                buckets["20-50"] += 1
            elif l <= 100:
                buckets["51-100"] += 1
            elif l <= 200:
                buckets["101-200"] += 1
            else:
                buckets[">200"] += 1
        avg = sum(lengths) / len(lengths) if lengths else 0
        return {"total": len(records), "avg_length": round(avg, 1), "buckets": buckets, "short": short}

    def engagement_report(self, min_retrievals: int = 5) -> dict:
        """Return retrieval-to-access click-through rates per memory.

        Memories with >= min_retrievals but CTR < 10% are flagged as low-engagement
        candidates for pruning or summary improvement.
        """
        records = self.get_all()
        low_ctr = []
        high_ctr = []
        untracked = 0
        for r in records:
            retrieved = r.get("times_retrieved", 0) or 0
            accessed = r.get("times_accessed", 0) or 0
            if retrieved < min_retrievals:
                untracked += 1
                continue
            ctr = accessed / retrieved
            entry = {
                "id": r["id"][:8],
                "summary": r.get("summary", "")[:80],
                "type": r.get("type", ""),
                "times_retrieved": retrieved,
                "times_accessed": accessed,
                "ctr": round(ctr, 3),
            }
            if ctr < 0.1:
                low_ctr.append(entry)
            else:
                high_ctr.append(entry)
        low_ctr.sort(key=lambda x: x["times_retrieved"], reverse=True)
        high_ctr.sort(key=lambda x: x["ctr"], reverse=True)
        return {
            "total": len(records),
            "untracked": untracked,
            "low_ctr": low_ctr,
            "high_ctr": high_ctr,
        }

    def count(self) -> int:
        return self.collection.count_rows()

    def get_all(self) -> list:
        return self.collection.to_arrow().to_pylist()

    def truncate(self, dry_run: bool = True, filter_repo: str | None = None) -> int:
        """Remove records from the store.

        - If `filter_repo` is provided, only records whose `repo` equals that value
          will be removed.
        - By default this is a dry-run and returns the number of records that
          would be deleted. Set `dry_run=False` to actually perform deletions.
        """
        all_records = self.get_all()
        to_delete = []
        for r in all_records:
            if filter_repo is not None and r.get("repo") != filter_repo:
                continue
            to_delete.append(r["id"])

        if dry_run:
            return len(to_delete)

        deleted = 0
        for mem_id in to_delete:
            try:
                self.delete(mem_id)
                deleted += 1
            except Exception:
                # keep going on errors to avoid partial failures blocking the whole operation
                pass

        return deleted

    # ── T1-D: Deprecation / Audit Trail ──────────────────────────────────────

    def forget(self, memory_id: str, reason: str = "") -> bool:
        """Mark a memory as deprecated — excludes it from all searches.

        The memory is preserved in the store with status='deprecated' and a
        deprecation_reason so it can be audited later. Use audit() to review
        deprecated memories. Use delete() to permanently remove after review.

        Returns True on success, False if memory_id not found.
        """
        safe_id = memory_id.replace("'", "''")
        record = self.get_by_id(memory_id, reinforce=False)
        if record is None:
            return False
        safe_reason = reason.replace("'", "''")
        with self._write_lock:
            self.collection.update(
                where=f"id = '{safe_id}'",
                values={"status": "deprecated", "deprecation_reason": reason},
            )
        _context_cache.invalidate()
        return True

    def get_deprecated(self) -> list:
        """Return all deprecated memories for the audit command."""
        try:
            results = (
                self.collection
                .search()
                .where("status = 'deprecated'")
                .limit(10000)
                .to_list()
            )
            return results
        except Exception:
            return []

    # ── T1-E: Store Health Dashboard ─────────────────────────────────────────

    def get_store_health(self) -> dict:
        """Return a comprehensive health report on the memory store.

        Metrics:
          - total: total memory count (active + deprecated)
          - active: count with status='active'
          - deprecated: count with status='deprecated'
          - type_breakdown: {type: count}
          - importance_histogram: bucketed importance distribution
          - avg_times_accessed: average explicit access count
          - stale_count: memories not accessed in the last 60 days (by creation timestamp)
          - low_ctr_count: retrieved 5+ times but accessed < 10% of the time
        """
        from datetime import datetime, timedelta
        all_records = self.get_all()
        total = len(all_records)
        deprecated = sum(1 for r in all_records if r.get("status") == "deprecated")
        active = total - deprecated

        type_breakdown: dict[str, int] = {}
        importance_hist = {"<0.3": 0, "0.3-0.5": 0, "0.5-0.7": 0, "0.7-0.9": 0, ">=0.9": 0}
        times_accessed_vals = []
        stale_count = 0
        low_ctr_count = 0
        cutoff = datetime.utcnow() - timedelta(days=60)

        for r in all_records:
            if r.get("status") == "deprecated":
                continue
            t = r.get("type", "unknown")
            type_breakdown[t] = type_breakdown.get(t, 0) + 1

            imp = r.get("importance", 0.5) or 0.5
            if imp < 0.3:
                importance_hist["<0.3"] += 1
            elif imp < 0.5:
                importance_hist["0.3-0.5"] += 1
            elif imp < 0.7:
                importance_hist["0.5-0.7"] += 1
            elif imp < 0.9:
                importance_hist["0.7-0.9"] += 1
            else:
                importance_hist[">=0.9"] += 1

            accessed = r.get("times_accessed", 0) or 0
            times_accessed_vals.append(accessed)

            ts = r.get("timestamp")
            if ts is not None:
                try:
                    ts_dt = ts if hasattr(ts, "date") else datetime.utcfromtimestamp(float(ts))
                    if ts_dt < cutoff and accessed == 0:
                        stale_count += 1
                except Exception:
                    pass

            retrieved = r.get("times_retrieved", 0) or 0
            if retrieved >= 5 and (accessed / retrieved) < 0.1:
                low_ctr_count += 1

        avg_accessed = round(sum(times_accessed_vals) / len(times_accessed_vals), 2) if times_accessed_vals else 0.0

        return {
            "total": total,
            "active": active,
            "deprecated": deprecated,
            "type_breakdown": type_breakdown,
            "importance_histogram": importance_hist,
            "avg_times_accessed": avg_accessed,
            "stale_count": stale_count,
            "low_ctr_count": low_ctr_count,
        }

    # ── T1-C: Memory Consolidation ────────────────────────────────────────────

    def consolidate(self, ids: list[str], summary: str | None = None) -> dict:
        """Merge multiple memories into one canonical memory.

        Fetches all memories by ids, combines their raw_text, uses the provided
        summary or falls back to the summary of the highest-importance memory.
        Stores a new memory at max(importance) and deletes the originals.

        Returns:
            {"status": "ok", "new_id": "...", "deleted": N}
            {"status": "error", "message": "..."} on failure.
        """
        from core.embeddings import embed
        import hashlib
        from datetime import datetime as _dt

        records = [self.get_by_id(mid, reinforce=False) for mid in ids]
        records = [r for r in records if r is not None]
        if len(records) < 2:
            return {"status": "error", "message": "Need at least 2 valid memory IDs to consolidate"}

        # Combined text: all raw_texts joined
        combined_raw = "\n\n---\n\n".join(r.get("raw_text", "") for r in records)

        # Use the provided summary, or the highest-importance memory's summary
        if not summary:
            best = max(records, key=lambda r: r.get("importance", 0.5) or 0.5)
            summary = best.get("summary", combined_raw[:200])

        max_importance = max((r.get("importance", 0.5) or 0.5) for r in records)
        all_tags = list({tag for r in records for tag in (r.get("tags") or [])})
        repo = next((r.get("repo") for r in records if r.get("repo")), None)
        mem_type = records[0].get("type", "agent_solution")

        new_id = hashlib.sha256(combined_raw[:500].encode()).hexdigest()

        from core.schema import Memory
        new_memory = Memory(
            id=new_id,
            type=mem_type,
            summary=summary[:200],
            raw_text=combined_raw,
            source="consolidation",
            repo=repo,
            timestamp=_dt.utcnow(),
            tags=all_tags + ["consolidated"],
            importance=max_importance,
        )

        if not self.exists(new_id):
            self.add(new_memory, embed(new_memory.summary))

        # Delete originals
        deleted = 0
        for r in records:
            try:
                self.delete(r["id"])
                deleted += 1
            except Exception:
                pass

        return {"status": "ok", "new_id": new_id, "deleted": deleted}