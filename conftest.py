"""
Root conftest — shared fixtures for all test packages.
"""
import pytest
import core.store_provider as _sp


@pytest.fixture
def store(tmp_path):
    """Isolated MemoryStore backed by a tmp directory.

    Patches the store_provider singleton so all get_store() calls
    within the test (including API routes, MCP tools, ContextEngine)
    return this isolated store automatically.
    """
    from core.memory_store import MemoryStore

    test_store = MemoryStore(db_path=str(tmp_path / "test_db"))
    original = _sp._store
    _sp._store = test_store
    yield test_store
    _sp._store = original
