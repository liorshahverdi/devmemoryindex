import importlib
import sys

import pytest


@pytest.fixture(autouse=True)
def clean_embeddings_module():
    sys.modules.pop("core.embeddings", None)
    yield
    sys.modules.pop("core.embeddings", None)


def _fresh_embeddings_import():
    sys.modules.pop("core.embeddings", None)
    return importlib.import_module("core.embeddings")


def test_embeddings_module_import_does_not_require_sentence_transformers(monkeypatch):
    """Lightweight commands can import core.embeddings without the heavy extra installed."""
    real_import_module = importlib.import_module

    def guarded_import_module(name, *args, **kwargs):
        if name == "sentence_transformers" or name.startswith("sentence_transformers."):
            raise ModuleNotFoundError("No module named 'sentence_transformers'")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", guarded_import_module)

    embeddings = _fresh_embeddings_import()

    assert hasattr(embeddings, "embed")
    assert hasattr(embeddings, "embed_batch")


def test_embed_reports_actionable_error_when_sentence_transformers_missing(monkeypatch):
    real_import_module = importlib.import_module

    def guarded_import_module(name, *args, **kwargs):
        if name == "sentence_transformers" or name.startswith("sentence_transformers."):
            raise ModuleNotFoundError("No module named 'sentence_transformers'")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", guarded_import_module)
    embeddings = _fresh_embeddings_import()

    with pytest.raises(RuntimeError) as exc:
        embeddings.embed("hello")

    message = str(exc.value)
    assert "requires sentence-transformers" in message
    assert "uv pip install -e '.[mcp]'" in message
    assert "BAAI/bge-small-en" in message


def test_embedding_model_initializes_only_on_first_embed_call(monkeypatch):
    calls = []

    class FakeModel:
        def __init__(self, model_name):
            calls.append(model_name)

        def encode(self, texts):
            if isinstance(texts, list):
                return [[1.0, 2.0, 3.0] for _ in texts]
            return [1.0, 2.0, 3.0]

    class FakeSentenceTransformersModule:
        SentenceTransformer = FakeModel

    monkeypatch.setitem(sys.modules, "sentence_transformers", FakeSentenceTransformersModule())
    embeddings = _fresh_embeddings_import()

    assert calls == []
    assert embeddings.embed("hello") == [1.0, 2.0, 3.0]
    assert calls == ["BAAI/bge-small-en"]
    assert embeddings.embed("again") == [1.0, 2.0, 3.0]
    assert calls == ["BAAI/bge-small-en"]
