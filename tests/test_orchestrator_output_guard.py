"""Unit tests for the orchestrator's unusable-output guard.

The guard ``_is_unusable_output`` exists so binary data and echoed prompt
wrappers produced by a misbehaving bound agent CLI are never written verbatim
into ``task_*.md`` reports — they corrupt the report and yield no source files.
"""

from __future__ import annotations

import pytest

from agentic_os.core.orchestrator import _is_unusable_output


def test_normal_markdown_result_is_usable() -> None:
    result = "Created the responsive theme.\n\n```css\n:root { --space-md: 1.5rem; }\n```\n"
    assert _is_unusable_output(result) is False


def test_prompt_wrapper_echo_is_unusable() -> None:
    """A CLI that prints the built mission wrapper back verbatim."""
    result = (
        "==================================================\n"
        "Mission Request\n"
        "Make the theme fully responsive.\n"
        "\n"
        "==================================================\n"
        "Assigned Task\n"
        "Implement frontend components.\n"
        "\n"
        "==================================================\n"
        "Task Title\n"
        "Frontend implementation\n"
        "\n"
        "==================================================\n"
        "CRITICAL INSTRUCTION FOR FILE CREATION\n"
        "You MUST create real source code files directly in the current directory.\n"
    )
    assert _is_unusable_output(result) is True


def test_bzip2_binary_decoded_text_is_unusable() -> None:
    """Compressed archive bytes decoded with errors='replace' -> garbage text."""
    # Header is the bzip2 magic; the rest is a compressed payload that fails
    # utf-8 decode and becomes replacement chars at high density.
    result = "BZh91AY&SY" + "����" * 40
    assert _is_unusable_output(result) is True


def test_null_byte_stream_is_unusable() -> None:
    assert _is_unusable_output("ab\x00\x00\x00\x00cd" * 20) is True


def test_empty_and_short_results_are_not_flagged() -> None:
    """Empty/None is handled by the upstream fallback, not this guard."""
    assert _is_unusable_output("") is False
    assert _is_unusable_output("[hermes] completed 'task'") is False


def test_plain_text_report_is_usable_even_if_long() -> None:
    body = "Inspected the workspace and documented findings.\n" * 50
    assert _is_unusable_output(body) is False


@pytest.mark.parametrize(
    "text",
    [
        "no markers here, just normal prose " * 20,
        "Task Title: some report mentioning a section\n" * 30,
    ],
)
def test_normal_prose_is_not_mistaken_for_echo(text: str) -> None:
    assert _is_unusable_output(text) is False
