from datetime import datetime

from core.memory_store import MemoryStore, VECTOR_DIM
from core.schema import Memory
from core.edge_store import EdgeStore
from daemon.jobs.edge_inference import run_edge_inference


def _vec(seed: float = 0.1) -> list[float]:
    return [seed] * VECTOR_DIM


def _add(store: MemoryStore, mem_id: str, memory_type: str, summary: str, raw_text: str, repo: str) -> None:
    store.add(
        Memory(
            id=mem_id,
            type=memory_type,
            summary=summary,
            raw_text=raw_text,
            source="test",
            repo=repo,
            timestamp=datetime.utcnow(),
            tags=[],
            importance=0.7,
        ),
        _vec(0.2),
    )


def _edges(db_path) -> list[dict]:
    return EdgeStore(str(db_path)).get_all_edges()


def test_links_test_failure_to_commit_by_test_name(tmp_path):
    db_path = tmp_path / "db"
    store = MemoryStore(str(db_path))
    _add(
        store,
        "failure-login",
        "failure_note",
        "pytest test_login.py::test_refreshes_token_on_401 failed",
        "FAILED tests/test_login.py::test_refreshes_token_on_401 - AssertionError: expected token refresh",
        "api",
    )
    _add(
        store,
        "commit-login",
        "git_commit",
        "Fix token refresh regression",
        "Fix failing tests/test_login.py::test_refreshes_token_on_401 by refreshing token on 401 responses",
        "api",
    )

    result = run_edge_inference(str(db_path))

    assert result["edges_added"] == 1
    assert {
        (e["from_id"], e["to_id"], e["edge_type"])
        for e in _edges(db_path)
    } == {("failure-login", "commit-login", "fixed_by")}


def test_links_similar_stack_traces_across_repos(tmp_path):
    db_path = tmp_path / "db"
    store = MemoryStore(str(db_path))
    stack = """Traceback (most recent call last):
  File "app/cache.py", line 42, in get_user
    return client.fetch(user_id)
TimeoutError: Redis request timed out after 30s
"""
    _add(
        store,
        "failure-api",
        "failure_note",
        "Redis timeout in API user lookup",
        stack,
        "api-service",
    )
    _add(
        store,
        "failure-worker",
        "failure_note",
        "Redis timeout in worker user lookup",
        stack.replace("app/cache.py", "worker/cache.py"),
        "worker-service",
    )

    run_edge_inference(str(db_path))

    assert ("failure-api", "failure-worker", "related_to") in {
        (e["from_id"], e["to_id"], e["edge_type"])
        for e in _edges(db_path)
    }


def test_links_failure_to_solution_by_stack_trace_signature(tmp_path):
    db_path = tmp_path / "db"
    store = MemoryStore(str(db_path))
    failure_text = """Traceback (most recent call last):
  File "core/memory_store.py", line 88, in add
    pa.Table.from_pylist(records, schema=schema)
pyarrow.lib.ArrowTypeError: object of type str cannot be converted to int
"""
    solution_text = """When add() raises pyarrow.lib.ArrowTypeError in core/memory_store.py,
normalize timestamp values before building the PyArrow table.
Traceback included File "core/memory_store.py", line 88, in add.
"""
    _add(
        store,
        "failure-arrow",
        "failure_note",
        "PyArrow type error in memory store add",
        failure_text,
        "devmemoryindex",
    )
    _add(
        store,
        "solution-arrow",
        "agent_solution",
        "Normalize timestamps before PyArrow writes",
        solution_text,
        "devmemoryindex",
    )

    run_edge_inference(str(db_path))

    assert ("failure-arrow", "solution-arrow", "references") in {
        (e["from_id"], e["to_id"], e["edge_type"])
        for e in _edges(db_path)
    }
