"""Tests for core/config.py — serialization round-trips and locking."""

import tomllib
from pathlib import Path

import pytest

from core.config import _to_toml, load, save, add_git_path, remove_git_path, CONFIG_PATH


# ── _to_toml serializer ───────────────────────────────────────────────────────


def test_to_toml_string():
    result = _to_toml({"llm": {"backend": "ollama"}})
    assert 'backend = "ollama"' in result


def test_to_toml_int():
    result = _to_toml({"schedule": {"git": 600}})
    assert "git = 600" in result
    # Must not be quoted
    assert 'git = "600"' not in result


def test_to_toml_float():
    """Floats must serialize without quotes so tomllib reads them back as float."""
    result = _to_toml({"ranking": {"importance": 0.85}})
    assert "importance = 0.85" in result
    assert 'importance = "0.85"' not in result


def test_to_toml_bool():
    """Booleans must serialize as TOML true/false, not Python 'True'/'False'."""
    result = _to_toml({"api": {"auth_enabled": True, "debug": False}})
    assert "auth_enabled = true" in result
    assert "debug = false" in result
    assert "True" not in result
    assert "False" not in result


def test_to_toml_bool_not_treated_as_int():
    """bool is a subclass of int; must be caught before the int branch."""
    result = _to_toml({"section": {"flag": True}})
    assert "flag = true" in result
    assert "flag = 1" not in result


def test_to_toml_empty_list():
    result = _to_toml({"git": {"repo_paths": []}})
    assert "repo_paths = []" in result


def test_to_toml_list():
    result = _to_toml({"git": {"repo_paths": ["/a", "/b"]}})
    assert '"/a"' in result
    assert '"/b"' in result


def test_to_toml_round_trip_float(tmp_path, monkeypatch):
    """Write a float via save(), read back via load() — must still be float."""
    cfg = tmp_path / "config.toml"
    monkeypatch.setattr("core.config.CONFIG_PATH", cfg)
    monkeypatch.setattr("core.config._LOCK_PATH", tmp_path / ".config.lock")

    save({"ranking": {"threshold": 0.75}})
    data = load()
    assert isinstance(data["ranking"]["threshold"], float)
    assert data["ranking"]["threshold"] == pytest.approx(0.75)


def test_to_toml_round_trip_bool(tmp_path, monkeypatch):
    """Write a bool via save(), read back via load() — must still be bool."""
    cfg = tmp_path / "config.toml"
    monkeypatch.setattr("core.config.CONFIG_PATH", cfg)
    monkeypatch.setattr("core.config._LOCK_PATH", tmp_path / ".config.lock")

    save({"api": {"auth_enabled": False}})
    data = load()
    assert data["api"]["auth_enabled"] is False


# ── concurrent safety (basic) ─────────────────────────────────────────────────


def test_save_creates_parent_directory(tmp_path, monkeypatch):
    cfg = tmp_path / "deep" / "nested" / "config.toml"
    monkeypatch.setattr("core.config.CONFIG_PATH", cfg)
    monkeypatch.setattr("core.config._LOCK_PATH", tmp_path / ".config.lock")

    save({"git": {"repo_paths": ["/x"]}})
    assert cfg.exists()


def test_add_remove_git_path_round_trip(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    monkeypatch.setattr("core.config.CONFIG_PATH", cfg)
    monkeypatch.setattr("core.config._LOCK_PATH", tmp_path / ".config.lock")

    from core.config import get_git_paths
    assert add_git_path("/projects/myapp") is True
    assert "/projects/myapp" in get_git_paths()
    assert add_git_path("/projects/myapp") is False  # already present
    assert remove_git_path("/projects/myapp") is True
    assert "/projects/myapp" not in get_git_paths()
