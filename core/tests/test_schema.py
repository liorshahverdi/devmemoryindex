from core.schema import Memory
from datetime import datetime


def test_memory_creation():
    memory = Memory(
        id="123",
        type="git_commit",
        summary="Fixed redis timeout in billing API",
        raw_text="diff --git a/billing.py b/billing.py\n...",
        source="/repos/billing-api",
        repo="billing-api",
        timestamp=datetime.now(),
        tags=["bugfix", "redis", "timeout"],
        importance=0.8,
    )

    assert memory.id == "123"
    assert memory.type == "git_commit"
    assert memory.summary == "Fixed redis timeout in billing API"
    assert memory.repo == "billing-api"
    assert memory.tags == ["bugfix", "redis", "timeout"]
    assert memory.importance == 0.8


def test_memory_default_importance():
    memory = Memory(
        id="456",
        type="terminal_command",
        summary="Ran database migration",
        raw_text="python manage.py migrate",
        source="/repos/backend",
        repo=None,
        timestamp=datetime.now(),
        tags=["migration"],
    )

    assert memory.importance == 0.5