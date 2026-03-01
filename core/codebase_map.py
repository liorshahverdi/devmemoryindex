"""
Codebase Map — Phase 7.8

Clusters file_content memories by vector similarity to discover subsystems.
Uses KMeans over stored embeddings; labels clusters by most common path prefix.

Required extras: uv add 'devmemoryindex[ml]'  (installs scikit-learn)
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path


def build_codebase_map(
    store,
    repo: str | None = None,
    n_clusters: int = 8,
) -> dict:
    """Cluster file_content memories to produce a structural codebase overview.

    Args:
        store:      MemoryStore instance.
        repo:       Optional repo filter. If None, uses all file_content memories.
        n_clusters: Target number of clusters (adjusted down if fewer files exist).

    Returns:
        dict with:
          - "clusters": list of {cluster_id, label, size, representative, files[]}
          - "total_files": total file_content memories clustered
          - "error": present only when clustering is not possible
    """
    try:
        import numpy as np
    except ImportError:
        return {"clusters": [], "error": "numpy not available — install with: uv add numpy"}
    try:
        from sklearn.cluster import KMeans
    except ImportError:
        return {
            "clusters": [],
            "error": "scikit-learn not available — install with: uv add 'devmemoryindex[ml]'",
        }

    records = store.get_all()
    files = [r for r in records if r.get("type") == "file_content"]
    if repo:
        files = [r for r in files if r.get("repo") == repo]

    if len(files) < 2:
        return {
            "clusters": [],
            "total_files": len(files),
            "error": "Not enough file_content memories to cluster (need at least 2)",
        }

    vectors = np.array([r["vector"] for r in files], dtype=np.float32)
    k = min(n_clusters, len(files))

    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(vectors)

    clusters = []
    for cluster_id in range(k):
        indices = [i for i, lbl in enumerate(labels) if lbl == cluster_id]
        if not indices:
            continue
        cluster_records = [files[i] for i in indices]

        # Representative: record closest to the cluster centroid
        centroid = km.cluster_centers_[cluster_id]
        cluster_vectors = vectors[indices]
        distances = np.linalg.norm(cluster_vectors - centroid, axis=1)
        rep_record = cluster_records[int(np.argmin(distances))]

        clusters.append({
            "cluster_id": cluster_id,
            "label": _cluster_label(cluster_records),
            "size": len(cluster_records),
            "representative": rep_record.get("summary", "")[:100],
            "files": [r.get("summary", "")[:80] for r in cluster_records[:5]],
        })

    clusters.sort(key=lambda c: c["size"], reverse=True)
    return {"clusters": clusters, "total_files": len(files)}


def _cluster_label(records: list[dict]) -> str:
    """Derive a human-readable label from the first directory component of file summaries.

    Summaries for file_content memories look like "core/memory_store.py (lines 1-80)".
    We extract the first path component (e.g. "core", "cli", "api") as the cluster label.
    Falls back to source-path parsing if summaries don't contain a path.
    """
    import re

    prefixes: list[str] = []

    # Primary: parse the leading directory from the summary's embedded path
    path_pattern = re.compile(r"^([\w.-]+)/([\w/.-]+)")
    for r in records:
        summary = (r.get("summary") or "").strip()
        m = path_pattern.match(summary)
        if m:
            prefixes.append(m.group(1))

    if prefixes:
        return Counter(prefixes).most_common(1)[0][0]

    # Secondary: parse the source field, skipping OS-level path components
    # (e.g. skip /Users/<name>/projects/<repo>/ to get the first project dir)
    _skip = {"Users", "home", "projects", "repos", "workspace", "src"}
    for r in records:
        source = (r.get("source") or "").strip()
        if source and source not in ("mcp_agent", "filesystem", ""):
            p = Path(source)
            for part in p.parts:
                if part not in ("/", ".", "..") and part not in _skip:
                    prefixes.append(part)
                    break

    if prefixes:
        return Counter(prefixes).most_common(1)[0][0]

    # Final fallback: first word of each summary
    words: list[str] = []
    for r in records:
        summary_words = (r.get("summary") or "").lower().split()
        if summary_words:
            words.append(summary_words[0])
    if words:
        return Counter(words).most_common(1)[0][0]

    return "cluster"
