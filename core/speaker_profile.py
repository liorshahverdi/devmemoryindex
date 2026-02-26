import json
import numpy as np
from pathlib import Path
from scipy.spatial.distance import cosine

PROFILE_PATH = Path.home() / ".devmemory" / "speaker_profile.json"


def save_profile(embedding: np.ndarray, path: Path = PROFILE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"embedding": embedding.tolist()}, f)


def load_profile(path: Path = PROFILE_PATH) -> np.ndarray:
    with open(path) as f:
        return np.array(json.load(f)["embedding"])


def is_self(segment_embedding: np.ndarray, profile: np.ndarray, threshold: float = 0.25) -> bool:
    """Cosine distance < threshold means same speaker. 0.25 is a practical starting point."""
    return cosine(segment_embedding, profile) < threshold
