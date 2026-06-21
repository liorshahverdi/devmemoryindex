import importlib
import os
import sys
from contextlib import contextmanager
from typing import Any, cast

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en"
_model: Any | None = None


@contextmanager
def _suppress_sentence_transformer_output():
    """Suppress noisy model-load diagnostics unless DEVMEMORY_VERBOSE is set."""
    if os.environ.get("DEVMEMORY_VERBOSE"):
        yield
        return

    # SentenceTransformer writes directly to OS file descriptors (bypassing
    # sys.stdout/stderr), so redirect at the fd level via os.dup2.
    _devnull_fd = os.open(os.devnull, os.O_WRONLY)
    _saved_stdout = os.dup(1)
    _saved_stderr = os.dup(2)
    os.dup2(_devnull_fd, 1)
    os.dup2(_devnull_fd, 2)
    os.close(_devnull_fd)
    try:
        yield
    finally:
        os.dup2(_saved_stdout, 1)
        os.dup2(_saved_stderr, 2)
        os.close(_saved_stdout)
        os.close(_saved_stderr)


def get_embedding_model():
    """Return the lazily initialized SentenceTransformer embedding model."""
    global _model
    if _model is not None:
        return _model

    try:
        sentence_transformers = importlib.import_module("sentence_transformers")
        SentenceTransformer = sentence_transformers.SentenceTransformer
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Embedding search requires sentence-transformers, but it is not installed. "
            "Install the appropriate extra, for example: uv pip install -e '.[mcp]' "
            "or uv pip install -e '.[dev]'. "
            f"The default embedding model is {DEFAULT_EMBEDDING_MODEL}."
        ) from exc

    try:
        with _suppress_sentence_transformer_output():
            _model = SentenceTransformer(DEFAULT_EMBEDDING_MODEL)
    except Exception as exc:
        offline_hint = " HF_HUB_OFFLINE is set, so downloads are disabled." if os.environ.get("HF_HUB_OFFLINE") else ""
        raise RuntimeError(
            f"Failed to load embedding model {DEFAULT_EMBEDDING_MODEL!r}." + offline_hint + " "
            "Run once with network access so sentence-transformers can cache the model, "
            "or pre-download it into the Hugging Face cache before using embedding commands offline. "
            "Set DEVMEMORY_VERBOSE=1 to show detailed model-load diagnostics."
        ) from exc
    return _model


def _as_list(encoded):
    return encoded.tolist() if hasattr(encoded, "tolist") else encoded


def embed(text: str) -> list:
    model = cast(Any, get_embedding_model())
    return _as_list(model.encode(text))


def embed_batch(texts: list) -> list:
    model = cast(Any, get_embedding_model())
    return _as_list(model.encode(texts))
