import importlib.abc
import json
from datetime import datetime

from core.schema import Memory


def _row(memory_id: str, summary: str, raw_text: str, repo: str = "devmemoryindex"):
    return {
        "id": memory_id,
        "type": "agent_solution",
        "summary": summary,
        "raw_text": raw_text,
        "source": "test",
        "repo": repo,
        "timestamp": datetime.utcnow().isoformat(),
        "tags": [],
        "importance": 0.9,
        "times_retrieved": 0,
        "times_accessed": 0,
        "status": "active",
        "deprecation_reason": None,
    }


class _BlockLanceDB(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "lancedb" or fullname.startswith("lancedb."):
            raise ModuleNotFoundError("No module named 'lancedb'", name="lancedb")
        return None


def test_backup_memory_store_imports_without_lancedb(monkeypatch):
    import sys
    sys.modules.pop("core.backup_read_store", None)
    sys.modules.pop("lancedb", None)
    blocker = _BlockLanceDB()
    monkeypatch.setattr(sys, "meta_path", [blocker, *sys.meta_path])

    from core.backup_read_store import BackupReadStore

    assert BackupReadStore is not None


def test_backup_memory_store_answers_text_search_without_lancedb(tmp_path):
    backup = tmp_path / "memories_latest.json"
    backup.write_text(json.dumps([
        _row("good", "DevMemoryIndex CLI QA fixes", "lazy-loading base installs optional dependencies", "devmemoryindex"),
        _row("bad", "browser cache fixes", "unrelated cache precision", "browser_jockey"),
    ]))

    from core.backup_read_store import BackupReadStore

    store = BackupReadStore(backup)
    results = store.text_search(
        "CLI QA base installs optional dependencies",
        k=5,
        type_filter="agent_solution",
        repo_filter="devmemoryindex",
    )

    assert [r["id"] for r in results] == ["good"]


def test_backup_memory_store_hybrid_search_uses_text_search(tmp_path):
    backup = tmp_path / "memories_latest.json"
    backup.write_text(json.dumps([
        _row("good", "base install optional dependency fix", "CLI QA lazy imports", "devmemoryindex"),
    ]))

    from core.backup_read_store import BackupReadStore

    store = BackupReadStore(backup)
    results = store.hybrid_search("CLI QA base installs", vector=[0.0] * 384, k=1)

    assert results[0]["id"] == "good"
