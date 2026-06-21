from datetime import datetime

from core.rag_engine import RAGEngine
from core.schema import Memory


class DummyStore:
    def __init__(self, memories):
        self.memories = memories

    def text_search(self, query, k=5, type_filter=None, repo_filter=None, speaker_filter=None):
        return self.memories[:k]


class ExplodingBackend:
    def chat(self, messages, stream=True):
        raise AssertionError("fast extractive ask must not call the LLM")


def _memory(raw_text: str, summary: str = "CLI QA fixes") -> dict:
    return {
        "id": "qa-memory-1",
        "type": "agent_solution",
        "summary": summary,
        "raw_text": raw_text,
        "repo": "devmemoryindex",
        "timestamp": datetime(2026, 6, 21),
        "importance": 0.9,
    }


def test_fast_ask_returns_extractive_answer_without_llm():
    store = DummyStore([
        _memory(
            "Resolved CLI QA issues by lazy-loading MemoryStore and voice dependencies "
            "so base install help does not require lancedb or numpy. Verification passed."
        )
    ])
    engine = RAGEngine(store, ExplodingBackend())

    answer, memories, planned = engine.ask_fast(
        "What CLI QA fixes were made for base installs?", repo="devmemoryindex", type_filter="agent_solution"
    )

    assert "lazy-loading MemoryStore" in answer
    assert "lancedb" in answer
    assert "numpy" in answer
    assert "[MEMORY-1]" in answer
    assert memories[0]["id"] == "qa-memory-1"
    assert planned == {}



def test_fast_ask_keeps_extract_under_requested_word_budget():
    verbose = (
        "Resolved high/medium DevMemoryIndex CLI QA issues by lazy-loading MemoryStore, "
        "voice dependencies, and connector imports so base install help does not require lancedb or numpy. "
        + "Extra implementation detail. " * 80
    )
    engine = RAGEngine(DummyStore([_memory(verbose)]), ExplodingBackend())

    answer, _memories, _planned = engine.ask_fast(
        "What CLI QA fixes were made for base installs? Keep answer under 80 words.",
        repo="devmemoryindex",
        type_filter="agent_solution",
    )

    assert len(answer.split()) <= 90  # allow citation marker plus an 80-word answer
    assert "lazy-loading MemoryStore" in answer
    assert "lancedb" in answer


def test_fast_ask_reports_when_no_memory_is_available():
    engine = RAGEngine(DummyStore([]), ExplodingBackend())

    answer, memories, _planned = engine.ask_fast("missing topic")

    assert memories == []
    assert "No relevant memories" in answer
