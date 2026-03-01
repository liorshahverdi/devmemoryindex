import json
import numpy as np
from datetime import datetime
from pathlib import Path
from scipy.spatial.distance import cosine

PROFILE_PATH = Path.home() / ".devmemory" / "speaker_profile.json"


def save_profile(
    embedding: np.ndarray,
    user_name: str | None = None,
    path: Path = PROFILE_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "embedding": embedding.tolist(),
        "enrolled_at": datetime.utcnow().isoformat(),
    }
    if user_name:
        data["user_name"] = user_name
    with open(path, "w") as f:
        json.dump(data, f)


def load_profile(path: Path = PROFILE_PATH) -> dict | None:
    """Return {"embedding": np.ndarray, "user_name": str|None} or None if not enrolled."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return {
            "embedding": np.array(data["embedding"]),
            "user_name": data.get("user_name"),
        }
    except Exception:
        return None


def is_self(segment_embedding: np.ndarray, profile, threshold: float = 0.25) -> bool:
    """Cosine distance < threshold means same speaker. 0.25 is a practical starting point.

    profile may be a dict (from load_profile) or a bare np.ndarray (legacy callers).
    """
    emb = profile["embedding"] if isinstance(profile, dict) else profile
    return cosine(segment_embedding, emb) < threshold
