"""Documentation tests for Hermes-specific DevMemoryIndex agent workflow."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_GUIDE = ROOT / "mcp_server" / "AGENT_GUIDE.md"
HERMES_WORKFLOW = ROOT / "docs" / "hermes-agent-workflow.md"
README = ROOT / "README.md"


def test_agent_guide_documents_recommended_tool_flow():
    text = AGENT_GUIDE.read_text()

    expected_steps = [
        "get_session_context",
        "search_memories",
        "get_memory",
        "build_context",
        "plan_task",
        "remember_memory",
        "remember_failure",
        "reinforce_memory",
        "update_memory",
        "forget_memory",
    ]
    for step in expected_steps:
        assert step in text

    assert "Do not call `get_session_context` repeatedly" in text
    assert "Do not store PR numbers" in text
    assert "Prefer storing root causes" in text


def test_hermes_workflow_doc_covers_registration_and_startup_prompt():
    text = HERMES_WORKFLOW.read_text()

    assert "hermes mcp add devmemory" in text
    assert "hermes mcp test devmemory" in text
    assert "At the start of complex repo work" in text
    assert "Before modifying this repo" in text
    assert "Hermes" in text
    assert "OpenAI/Pi" in text


def test_readme_links_hermes_workflow_doc():
    readme = README.read_text()

    assert "docs/hermes-agent-workflow.md" in readme
