
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

def compute_score(result: dict) -> float:
    semantic = 1 - result.get("_distance", 1.0)
    importance = result.get("importance", 0.5)
    recency = recency_score(result["timestamp"])
    return semantic * 0.75 + importance * 0.15 + recency * 0.10