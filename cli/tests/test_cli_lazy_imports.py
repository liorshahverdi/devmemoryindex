import builtins
import importlib
import sys


def test_cli_main_import_does_not_require_sentence_transformers(monkeypatch):
    """Help/setup commands should remain importable without embedding dependencies."""
    sys.modules.pop("cli.main", None)
    sys.modules.pop("core.embeddings", None)
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "sentence_transformers" or name.startswith("sentence_transformers."):
            raise ModuleNotFoundError("No module named 'sentence_transformers'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    module = importlib.import_module("cli.main")

    assert module.app.info.name == "devmemory"
