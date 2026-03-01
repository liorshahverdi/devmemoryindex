"""
Plan Engine — Phase 7.9

Generates a grounded implementation plan by combining:
  - Relevant memories from the index (via ContextEngine)
  - Current git state (diff stat + recent commits)
  - The task description

Calls the configured LLM backend (Ollama by default) to synthesize the plan.

Required: LLM backend running (devmemory config set llm.backend ollama)
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_git_context() -> str:
    """Return recent commits + current diff stat as a compact string."""
    parts = []
    try:
        log = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if log:
            parts.append(f"Recent commits:\n{log}")
    except Exception:
        pass
    try:
        diff = subprocess.run(
            ["git", "diff", "--stat"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if diff:
            parts.append(f"Staged/unstaged changes:\n{diff}")
    except Exception:
        pass
    return "\n\n".join(parts)


def plan_task(
    description: str,
    memory_context: str,
    git_context: str,
    files: list[str] | None = None,
) -> str:
    """Call the LLM backend to produce a grounded implementation plan.

    Args:
        description:    Plain-language description of the task.
        memory_context: Relevant past solutions/decisions as a flat text block.
        git_context:    Current git state (commits + diff stat).
        files:          Optional list of files being edited.

    Returns:
        Plan text as a markdown string.

    Raises:
        RuntimeError if the LLM backend call fails.
    """
    from core.llm_backend import get_backend

    file_section = ""
    if files:
        file_section = "\nFiles I'm editing:\n" + "\n".join(f"  - {f}" for f in files)

    prompt_parts = [
        "You are a senior software engineer. Given the task description below, "
        "produce a concise numbered step-by-step implementation plan.",
        "Ground your plan in the relevant past memories and current git context provided. "
        "Avoid steps that repeat past mistakes shown in the context.",
        "",
        f"## Task\n{description}{file_section}",
    ]
    if memory_context and memory_context.strip():
        prompt_parts.append(f"\n## Relevant Past Context\n{memory_context}")
    if git_context and git_context.strip():
        prompt_parts.append(f"\n## Current Git State\n{git_context}")
    prompt_parts.append(
        "\n## Plan\n"
        "Provide a numbered step-by-step plan. Be specific about which files to modify, "
        "what functions to add or change, and key implementation details. "
        "Keep it focused and under 500 words."
    )

    prompt = "\n".join(prompt_parts)

    try:
        backend = get_backend()
        chunks = list(backend.generate(prompt, stream=False))
        return "".join(chunks).strip()
    except Exception as e:
        raise RuntimeError(f"LLM backend error: {e}") from e
