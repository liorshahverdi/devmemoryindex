"""
Context Engine

Responsible for:
- Turning search results into AI-friendly context
- Hybrid ranking (importance + recency)
- Token budget packing
- Formatting memories for LLM consumption

DOES NOT:
- Perform embeddings
- Query LanceDB directly.
- Estimate tokens (delegated)
"""

from datetime import datetime, timezone
from typing import List, Dict, Any

from core.schema import Memory
from core.token_budget import pack_within_budget

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
DEFAULT_TOKEN_BUDGET = 4000

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _parse_memory(row: Dict[str, Any]) -> Memory:
    """Convert a LanceDB row into a Memory object."""
    timestamp = row.get("timestamp")

    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except Exception:
            timestamp = datetime.now(timezone.utc)
    
    return Memory(
        id=row.get("id"),
        type=row.get("type"),
        repo=row.get("repo"),
        content=row.get("content"),
        importance=row.get("importance", 0.5),
        timestamp=timestamp,
        
    )