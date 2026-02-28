import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-small-en")

def embed(text: str) -> list:
    return model.encode(text).tolist()

def embed_batch(texts: list) -> list:
    return model.encode(texts).tolist()