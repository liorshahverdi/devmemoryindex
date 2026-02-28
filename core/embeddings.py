import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")

from sentence_transformers import SentenceTransformer

# SentenceTransformer prints noisy weight-load diagnostics to stderr.
# Suppress them unless DEVMEMORY_VERBOSE is set.
if os.environ.get("DEVMEMORY_VERBOSE"):
    model = SentenceTransformer("BAAI/bge-small-en")
else:
    # The library writes directly to OS file descriptors (bypassing sys.stdout/stderr),
    # so we must redirect at the fd level via os.dup2.
    _devnull_fd = os.open(os.devnull, os.O_WRONLY)
    _saved_stdout = os.dup(1)
    _saved_stderr = os.dup(2)
    os.dup2(_devnull_fd, 1)
    os.dup2(_devnull_fd, 2)
    os.close(_devnull_fd)
    try:
        model = SentenceTransformer("BAAI/bge-small-en")
    finally:
        os.dup2(_saved_stdout, 1)
        os.dup2(_saved_stderr, 2)
        os.close(_saved_stdout)
        os.close(_saved_stderr)

def embed(text: str) -> list:
    return model.encode(text).tolist()

def embed_batch(texts: list) -> list:
    return model.encode(texts).tolist()