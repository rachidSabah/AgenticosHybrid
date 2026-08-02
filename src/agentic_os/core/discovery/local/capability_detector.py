"""Capability detector for local agent discovery.

Maps a *tool_type* (and optionally its version) to one or more
:class:`AgentCapability` values.
"""

from __future__ import annotations

import logging
from typing import Any

from agentic_os.domain.discovery import AgentCapability

log = logging.getLogger("agentic_os.local_discovery.capability_detector")

# ── Tool-type → default capability set ─────────────────────────────
# These are the "safe" assumptions about what each tool can do.
_CAPABILITY_MAP: dict[str, tuple[AgentCapability, ...]] = {
    "hermes": (
        AgentCapability.CODE_GENERATION,
        AgentCapability.CHAT,
        AgentCapability.MCP,
        AgentCapability.FILE_OPS,
        AgentCapability.TERMINAL_OPS,
        AgentCapability.REASONING,
    ),
    "claude-code": (
        AgentCapability.CODE_GENERATION,
        AgentCapability.CHAT,
        AgentCapability.FILE_OPS,
        AgentCapability.TERMINAL_OPS,
        AgentCapability.REASONING,
        AgentCapability.MCP,
    ),
    "codex": (
        AgentCapability.CODE_GENERATION,
        AgentCapability.TESTING,
        AgentCapability.REASONING,
        AgentCapability.TERMINAL_OPS,
    ),
    "gemini-cli": (
        AgentCapability.CODE_GENERATION,
        AgentCapability.CHAT,
        AgentCapability.REASONING,
    ),
    "opencode": (
        AgentCapability.CODE_GENERATION,
        AgentCapability.CHAT,
        AgentCapability.TERMINAL_OPS,
    ),
    "aider": (
        AgentCapability.CODE_GENERATION,
        AgentCapability.FILE_OPS,
        AgentCapability.TERMINAL_OPS,
        AgentCapability.CODE_REVIEW,
    ),
    "continue": (
        AgentCapability.CHAT,
        AgentCapability.CODE_GENERATION,
        AgentCapability.CODE_REVIEW,
        AgentCapability.MCP,
    ),
    "openhands": (
        AgentCapability.CODE_GENERATION,
        AgentCapability.TERMINAL_OPS,
        AgentCapability.BROWSER_OPS,
        AgentCapability.FILE_OPS,
    ),
    "ollama": (
        AgentCapability.CHAT,
        AgentCapability.EMBEDDINGS,
        AgentCapability.REASONING,
    ),
    "lm-studio": (
        AgentCapability.CHAT,
        AgentCapability.EMBEDDINGS,
        AgentCapability.REASONING,
    ),
    "vllm": (
        AgentCapability.CHAT,
        AgentCapability.EMBEDDINGS,
        AgentCapability.REASONING,
    ),
    "docker": (
        AgentCapability.CUSTOM,  # Container orchestration
    ),
    "git": (
        AgentCapability.FILE_OPS,
        AgentCapability.CUSTOM,  # Version control
    ),
    "python": (
        AgentCapability.CODE_GENERATION,
        AgentCapability.TESTING,
        AgentCapability.REASONING,
        AgentCapability.FILE_OPS,
    ),
    "node": (
        AgentCapability.CODE_GENERATION,
        AgentCapability.TESTING,
    ),
    "vscode-cli": (
        AgentCapability.CODE_GENERATION,
        AgentCapability.CODE_REVIEW,
        AgentCapability.CHAT,
        AgentCapability.TERMINAL_OPS,
        AgentCapability.FILE_OPS,
    ),
}


class CapabilityDetector:
    """Infer :class:`AgentCapability` values from a tool type and version.

    Version-specific overrides can be added later without breaking the
    interface — currently uses a static map.
    """

    def detect(
        self,
        tool_type: str,
        version: str = "",
        extra: dict[str, Any] | None = None,
    ) -> tuple[AgentCapability, ...]:
        """Return the capability tuple for *tool_type*.

        Args:
            tool_type: The tool identifier (e.g. ``"hermes"``).
            version: Optional version string for future version-aware logic.
            extra: Optional extra metadata for future extension.

        Returns:
            A tuple of :class:`AgentCapability` values.  Empty tuple
            if the tool type is unknown.

        Complexity: O(1) — dict lookup.
        """
        caps = _CAPABILITY_MAP.get(tool_type)
        if caps is not None:
            return caps

        log.warning("Unknown tool_type '%s' — returning empty capabilities", tool_type)
        return ()

    def detect_batch(
        self,
        tools: list[tuple[str, str]],
    ) -> list[tuple[str, tuple[AgentCapability, ...]]]:
        """Batch-detect capabilities for multiple tools.

        Args:
            tools: List of ``(tool_type, version)`` pairs.

        Returns:
            List of ``(tool_type, capabilities)`` tuples.

        Complexity: O(*n*) — linear in input size.
        """
        return [(tool_type, self.detect(tool_type, version)) for tool_type, version in tools]
