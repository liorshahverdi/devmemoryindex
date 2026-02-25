import pytest
from datetime import datetime
from core.memory_store import MemoryStore, VECTOR_DIM
from core.schema import Memory


@pytest.fixture
def store(tmp_path):
    """Create a MemoryStore backed by a temp directory for testing."""
    return MemoryStore(db_path=str(tmp_path))


@pytest.fixture
def sample_memory():
    """Create a sample Memory object for testing."""
    return Memory(
        id="test-1",
        type="code_snippet",
        summary="Redis timeout handling",
        raw_text="SET key value EX 300",
        source="redis_docs.md",
        repo="devmemoryindex",
        timestamp=datetime.now().isoformat(),
        tags=["redis", "timeout"],
        importance=0.8
    )


@pytest.fixture
def sample_vector():
    """Create a sample 384-dim embedding vector."""
    return [0.1] * VECTOR_DIM


def test_add_memory(store, sample_memory, sample_vector):
    """Test that add inserts the correct data into the store."""
    store.add(sample_memory, sample_vector)

    assert store.count() == 1
    rows = store.get_all()
    assert rows[0]["id"] == "test-1"
    assert rows[0]["type"] == "code_snippet"
    assert rows[0]["summary"] == "Redis timeout handling"


def test_add_and_search_memory(store, sample_memory, sample_vector):
    """Test saving a memory and retrieving it via semantic search."""
    store.add(sample_memory, sample_vector)

    results = store.semantic_search(sample_vector, k=1)

    assert len(results) == 1
    assert results[0]["id"] == "test-1"
    assert results[0]["summary"] == "Redis timeout handling"
    assert results[0]["tags"] == ["redis", "timeout"]
    assert results[0]["importance"] == pytest.approx(0.8)


def test_search_multiple_memories(store, sample_vector):
    """Test searching across multiple saved memories returns ranked results."""
    memories = [
        Memory(
            id="m1", type="git_commit", summary="Fix billing bug",
            raw_text="diff --git ...", source="billing.py",
            repo="billing-api", timestamp=datetime.now().isoformat(),
            tags=["bugfix"], importance=0.9
        ),
        Memory(
            id="m2", type="terminal_command", summary="Run migration",
            raw_text="python manage.py migrate", source="terminal",
            repo=None, timestamp=datetime.now().isoformat(),
            tags=["migration"], importance=0.5
        ),
    ]
    for mem in memories:
        store.add(mem, sample_vector)

    results = store.semantic_search(sample_vector, k=2)
    assert len(results) == 2
    returned_ids = {r["id"] for r in results}
    assert returned_ids == {"m1", "m2"}