"""Regression tests for CLI QA findings."""

import builtins
import importlib
import os
import sys
from pathlib import Path

import typer
from typer.testing import CliRunner


def test_cli_main_import_does_not_require_lancedb(monkeypatch):
    """Help/setup commands should remain importable without LanceDB installed."""
    for name in ["cli.main", "core.store_provider", "core.memory_store", "connectors.base"]:
        sys.modules.pop(name, None)
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "lancedb" or name.startswith("lancedb."):
            raise ModuleNotFoundError("No module named 'lancedb'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    module = importlib.import_module("cli.main")

    assert module.app.info.name == "devmemory"


def test_cli_main_import_does_not_require_voice_profile_dependencies(monkeypatch):
    """Base CLI help should not require optional voice enrollment dependencies."""
    for name in ["cli.main", "cli.commands.enroll", "core.speaker_profile"]:
        sys.modules.pop(name, None)
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "numpy" or name.startswith("numpy."):
            raise ModuleNotFoundError("No module named 'numpy'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    module = importlib.import_module("cli.main")

    assert module.app.info.name == "devmemory"


def test_store_provider_import_does_not_require_lancedb(monkeypatch):
    """Importing the provider should be lightweight; DB deps load only on get_store()."""
    for name in ["core.store_provider", "core.memory_store"]:
        sys.modules.pop(name, None)
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "lancedb" or name.startswith("lancedb."):
            raise ModuleNotFoundError("No module named 'lancedb'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    module = importlib.import_module("core.store_provider")

    assert callable(module.get_store)


def test_embeddings_import_does_not_force_huggingface_offline(monkeypatch):
    """First-run embedding commands should be allowed to download/cache the model."""
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    sys.modules.pop("core.embeddings", None)

    importlib.import_module("core.embeddings")

    assert "HF_HUB_OFFLINE" not in os.environ


def test_ingest_help_lists_all_registered_cli_connectors():
    """The --source help text should not omit valid registry connector names."""
    from cli.commands.ingest import ingest
    from connectors.registry import ALL_CONNECTORS

    app = typer.Typer()
    app.command()(ingest)
    result = CliRunner().invoke(app, ["ingest", "--help"])

    assert result.exit_code == 0
    for connector_cls in ALL_CONNECTORS:
        assert connector_cls.name in result.output


def test_readme_cli_examples_match_current_options():
    """Documented commands should not advertise removed add/prune options."""
    readme = Path(__file__).resolve().parents[2] / "README.md"
    text = readme.read_text()

    assert "devmemory add --summary" not in text
    assert "--min-importance" not in text
