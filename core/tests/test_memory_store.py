import pytest
import tempfile
import lancedb
from datetime import datetime
from core.memory_store import save_memory, search_memory, _schema, VECTOR_DIM
from core.schema import Memory


@pytest.fixture
def collection(tmp_path):
    """Create a LanceDB table in a temp directory for testing."""
    db = lancedb.connect(str(tmp_path))
    return db.create_table("memories", schema=_schema)


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


def test_save_memory(collection, sample_memory, sample_vector):
    """Test that save_memory inserts the correct data into the collection."""
    save_memory(sample_memory, sample_vector, collection=collection)

    rows = collection.to_arrow().to_pydict()
    assert len(rows["id"]) == 1
    assert rows["id"][0] == "test-1"
    assert rows["type"][0] == "code_snippet"
    assert rows["summary"][0] == "Redis timeout handling"


def test_save_memory_with_search(collection, sample_memory, sample_vector):
    """Test saving a memory and retrieving it via search."""
    save_memory(sample_memory, sample_vector, collection=collection)

    results = search_memory(sample_vector, n_results=1, collection=collection)

    assert len(results) == 1
    assert results[0]["id"] == "test-1"
    assert results[0]["summary"] == "Redis timeout handling"
    assert results[0]["tags"] == ["redis", "timeout"]
    assert results[0]["importance"] == pytest.approx(0.8)


def test_search_multiple_memories(collection, sample_vector):
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
        save_memory(mem, sample_vector, collection=collection)

    results = search_memory(sample_vector, n_results=2, collection=collection)
    # print("\n=== Search Results ===")
    # for r in results:
    #     print (r)
    # assert len(results) == 2
    returned_ids = {r["id"] for r in results}
    assert returned_ids == {"m1", "m2"}