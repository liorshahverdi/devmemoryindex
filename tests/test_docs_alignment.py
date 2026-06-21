"""Documentation alignment tests for public examples and roadmap headings."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()
ROADMAP = (ROOT / "ROADMAP.md").read_text()


ACTIVE_CONNECTOR_SOURCES = [
    "git",
    "diff",
    "terminal",
    "filesystem",
    "markdown",
    "claude",
    "copilot",
    "browser",
    "meeting",
]


def test_readme_documents_actual_webhook_ingest_endpoint_and_payload():
    assert "/webhook/ingest" not in README
    assert "http://localhost:7711/memory/ingest" in README
    assert '"text"' in README
    assert '"memory_type"' in README
    assert '"summary"' not in README.partition("# Ingest via webhook")[2].partition("# Long texts")[0]


def test_readme_lists_all_active_ingest_sources():
    for source in ACTIVE_CONNECTOR_SOURCES:
        assert f"devmemory ingest --source {source}" in README
        assert f"| `{source}` |" in README


def test_roadmap_has_unique_top_level_phase_numbers():
    phase_numbers = re.findall(r"^## Phase (\d+)\b", ROADMAP, flags=re.MULTILINE)
    duplicates = {n for n in phase_numbers if phase_numbers.count(n) > 1}
    assert duplicates == set()
