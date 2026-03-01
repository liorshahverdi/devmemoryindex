
# Scoring formula:
# ```
# final_score = semantic_similarity * 0.75
#             + importance * 0.15
#             + recency * 0.10
# ```
from datetime import datetime
import math

def recency_score(timestamp: datetime) -> float:
    age_hours = (datetime.utcnow() - timestamp).total_seconds() / 3600
    return math.exp(-age_hours / (30 * 24))  # decay over ~30 days

def compute_score_breakdown(result: dict) -> dict:
    """Return individual score components for explainability.

    Returns:
        {
            "semantic": float,    # 1 - cosine distance (vector similarity)
            "importance": float,  # stored importance value
            "recency": float,     # exponential decay over 30 days
            "final": float,       # weighted sum (0.75/0.15/0.10)
        }
    """
    semantic = max(0.0, 1.0 - result.get("_distance", 1.0))
    importance = result.get("importance", 0.5)
    recency = recency_score(result["timestamp"])
    final = semantic * 0.75 + importance * 0.15 + recency * 0.10
    return {
        "semantic": round(semantic, 4),
        "importance": round(importance, 4),
        "recency": round(recency, 4),
        "final": round(final, 4),
    }

def compute_score(result: dict) -> float:
    return compute_score_breakdown(result)["final"]