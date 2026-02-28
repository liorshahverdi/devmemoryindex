import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")

from sentence_transformers import SentenceTransformer

# SentenceTransformer prints noisy weight-load diagnostics to stderr.
# Suppress them unless DEVMEMORY_VERBOSE is set.
if os.environ.get("DEVMEMORY_VERBOSE"):
    model = SentenceTransformer("BAAI/bge-small-en")
else:
    with open(os.devnull, "w") as _devnull:
        _stderr, sys.stderr = sys.stderr, _devnull
        try:
            model = SentenceTransformer("BAAI/bge-small-en")
        finally:
            sys.stderr = _stderr

def embed(text: str) -> list:
    return model.encode(text).tolist()

def embed_batch(texts: list) -> list:
    return model.encode(texts).tolist()