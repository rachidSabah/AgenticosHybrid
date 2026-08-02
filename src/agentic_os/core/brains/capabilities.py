"""BrainCapabilityAnalyzer — maps brain metadata to capability strings.

Translates a brain's type, vendor, runtime, and model information into
a canonical set of capability strings that can be used for routing and
discovery.
"""

from __future__ import annotations

from agentic_os.domain.brains import (
    BrainRecord,
    BrainRuntime,
    BrainType,
    BrainVendor,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("brains.capabilities")


class BrainCapabilityAnalyzer:
    """Analyse a :class:`BrainRecord` and produce a canonical set of
    capability strings.

    Capabilities describe what a brain *can do*, independent of its
    current health or status.  Examples: ``"chat"``, ``"vision"``,
    ``"code_execution"``, ``"tool_use"``, ``"streaming"``.

    This class provides both declarative vendor-based capability maps
    and dynamic analysis from a brain record's supported models and
    tools.

    Thread-safety
    -------------
    Stateless by design — all methods are safe to call concurrently.
    """

    # ── Vendor capability maps ──────────────────────────────────────────────

    _VENDOR_CAPABILITIES: dict[BrainVendor, tuple[str, ...]] = {
        BrainVendor.OPENAI: (
            "chat",
            "completion",
            "embeddings",
            "vision",
            "function_calling",
            "streaming",
            "json_mode",
            "structured_output",
        ),
        BrainVendor.ANTHROPIC: (
            "chat",
            "vision",
            "tool_use",
            "streaming",
            "extended_thinking",
            "prompt_caching",
        ),
        BrainVendor.GOOGLE: (
            "chat",
            "vision",
            "tool_use",
            "streaming",
            "code_execution",
            "grounding",
        ),
        BrainVendor.MISTRAL: (
            "chat",
            "completion",
            "embeddings",
            "function_calling",
            "streaming",
            "agentic",
        ),
        BrainVendor.GROQ: ("chat", "streaming", "fast_inference"),
        BrainVendor.AZURE: (
            "chat",
            "completion",
            "embeddings",
            "vision",
            "function_calling",
            "streaming",
            "json_mode",
        ),
        BrainVendor.AWS: ("chat", "completion", "embeddings", "tool_use"),
        BrainVendor.VERTEX: (
            "chat",
            "vision",
            "streaming",
            "embeddings",
            "tool_use",
        ),
        BrainVendor.OPENROUTER: (
            "chat",
            "streaming",
            "function_calling",
            "multi_provider",
        ),
        BrainVendor.OLLAMA: (
            "chat",
            "completion",
            "embeddings",
            "streaming",
            "local_inference",
        ),
        BrainVendor.DEEPSEEK: (
            "chat",
            "completion",
            "streaming",
            "reasoning",
        ),
        BrainVendor.HERMES: (
            "chat",
            "tool_use",
            "multi_agent",
            "plugin_system",
        ),
        BrainVendor.CLAUDE_CODE: (
            "chat",
            "tool_use",
            "code_generation",
            "file_editing",
            "terminal_access",
        ),
        BrainVendor.GEMINI_CLI: (
            "chat",
            "vision",
            "code_generation",
            "tool_use",
        ),
        BrainVendor.CODEX: (
            "chat",
            "code_generation",
            "file_editing",
        ),
        BrainVendor.OPENCODE: (
            "chat",
            "code_generation",
            "file_editing",
            "search",
        ),
        BrainVendor.AIDER: (
            "chat",
            "code_generation",
            "file_editing",
            "git_integration",
        ),
        BrainVendor.CONTINUE: (
            "chat",
            "code_generation",
            "completion",
            "tool_use",
            "context_provider",
        ),
        BrainVendor.GITHUB_COPILOT: (
            "completion",
            "chat",
            "code_generation",
        ),
        BrainVendor.CURSOR: (
            "chat",
            "completion",
            "code_generation",
            "file_editing",
            "agentic",
        ),
    }

    # ── BrainType capability maps ───────────────────────────────────────────

    _BRAIN_TYPE_CAPABILITIES: dict[BrainType, tuple[str, ...]] = {
        BrainType.LOCAL_CLI: (
            "local",
            "cli",
            "code_generation",
            "file_editing",
            "terminal_access",
        ),
        BrainType.CLOUD_API: ("cloud", "api", "remote_inference"),
        BrainType.ORCHESTRATOR: (
            "orchestrator",
            "multi_agent",
            "workflow",
            "planning",
            "delegation",
        ),
        BrainType.MCP_SERVER: ("mcp", "tool_provision", "resource_access"),
        BrainType.CUSTOM: ("custom",),
    }

    # ── Runtime capability maps ─────────────────────────────────────────────

    _RUNTIME_CAPABILITIES: dict[BrainRuntime, tuple[str, ...]] = {
        BrainRuntime.PYTHON: ("python_runtime",),
        BrainRuntime.NODE: ("node_runtime",),
        BrainRuntime.GO: ("go_runtime",),
        BrainRuntime.RUST: ("rust_runtime",),
        BrainRuntime.CONTAINER: ("containerized",),
        BrainRuntime.NATIVE: ("native",),
        BrainRuntime.CLOUD: ("cloud_runtime",),
        BrainRuntime.UNKNOWN: (),
        BrainRuntime.BUN: ("bun_runtime",),
        BrainRuntime.DENO: ("deno_runtime",),
    }

    # ── Public API ──────────────────────────────────────────────────────────

    def analyze(self, record: BrainRecord) -> tuple[str, ...]:
        """Return a deduplicated tuple of capability strings for a brain.

        Combines capabilities derived from the brain's vendor, type,
        runtime, supported models, and supported tools.

        Args:
            record: The brain record to analyse.

        Returns:
            A deduplicated, sorted tuple of capability strings.
        """
        capabilities: set[str] = set()

        # Vendor capabilities
        vendor_caps = self._VENDOR_CAPABILITIES.get(record.vendor, ())
        capabilities.update(vendor_caps)

        # Brain-type capabilities
        type_caps = self._BRAIN_TYPE_CAPABILITIES.get(record.brain_type, ())
        capabilities.update(type_caps)

        # Runtime capabilities
        runtime_caps = self._RUNTIME_CAPABILITIES.get(record.runtime, ())
        capabilities.update(runtime_caps)

        # Supported models → "model:<name>" capabilities
        for model in record.supported_models:
            capabilities.add(f"model:{model}")

        # Supported tools → "tool:<name>" capabilities
        for tool in record.supported_tools:
            capabilities.add(f"tool:{tool}")

        # Already-set capabilities from the record itself
        capabilities.update(record.capabilities)

        return tuple(sorted(capabilities))

    def get_vendor_capabilities(self, vendor: BrainVendor) -> tuple[str, ...]:
        """Return the known capabilities for a given vendor.

        Args:
            vendor: The vendor to query.

        Returns:
            A tuple of capability strings, or an empty tuple if the
            vendor is unknown.
        """
        return self._VENDOR_CAPABILITIES.get(vendor, ())

    def get_type_capabilities(self, brain_type: BrainType) -> tuple[str, ...]:
        """Return the capabilities associated with a brain type."""
        return self._BRAIN_TYPE_CAPABILITIES.get(brain_type, ())

    def get_runtime_capabilities(self, runtime: BrainRuntime) -> tuple[str, ...]:
        """Return the capabilities associated with a runtime."""
        return self._RUNTIME_CAPABILITIES.get(runtime, ())

    def has_capability(self, record: BrainRecord, capability: str) -> bool:
        """Check if a brain record has a specific capability.

        Args:
            record: The brain record to check.
            capability: The capability string to look for (e.g. ``"vision"``).

        Returns:
            ``True`` if the capability is present.
        """
        return capability in self.analyze(record)

    def match_capabilities(
        self,
        records: list[BrainRecord],
        required: set[str],
        *,
        require_all: bool = True,
    ) -> list[BrainRecord]:
        """Filter brain records by required capabilities.

        Args:
            records: The list of brains to filter.
            required: Set of capability strings that must be present.
            require_all: When ``True`` (default), a brain must have all
                required capabilities.  When ``False``, any one suffices.

        Returns:
            A filtered list of :class:`BrainRecord` objects.
        """
        if not required:
            return list(records)

        results: list[BrainRecord] = []
        for record in records:
            caps = set(self.analyze(record))
            if require_all:
                if required.issubset(caps):
                    results.append(record)
            else:
                if required & caps:
                    results.append(record)
        return results
