"""Tests for BrainCapabilityAnalyzer — maps brain metadata to capability strings.

Covers analyze, has_capability, match_capabilities, and per-vendor/type/runtime
capability queries.
"""

from __future__ import annotations

import pytest

from agentic_os.core.brains.capabilities import BrainCapabilityAnalyzer
from agentic_os.domain.brains import (
    BrainRecord,
    BrainRuntime,
    BrainStatus,
    BrainType,
    BrainVendor,
)


@pytest.fixture
def analyzer() -> BrainCapabilityAnalyzer:
    return BrainCapabilityAnalyzer()


# ═══════════════════════════════════════════════════════════════════════
# analyze() — full capability derivation
# ═══════════════════════════════════════════════════════════════════════


class TestBrainCapabilityAnalyzerAnalyze:
    """analyze() — derives capabilities from vendor, type, runtime, models, tools."""

    def test_openai_cloud_brain(self, analyzer: BrainCapabilityAnalyzer) -> None:
        record = BrainRecord(
            id="o1",
            display_name="GPT-4o",
            brain_type=BrainType.CLOUD_API,
            vendor=BrainVendor.OPENAI,
            runtime=BrainRuntime.CLOUD,
            version="4.0",
            status=BrainStatus.CONNECTED,
        )
        caps = analyzer.analyze(record)
        assert "chat" in caps
        assert "vision" in caps
        assert "streaming" in caps
        assert "cloud" in caps
        assert "api" in caps
        assert "cloud_runtime" in caps

    def test_ollama_local_brain(self, analyzer: BrainCapabilityAnalyzer) -> None:
        record = BrainRecord(
            id="ol1",
            display_name="Llama",
            brain_type=BrainType.LOCAL_CLI,
            vendor=BrainVendor.OLLAMA,
            runtime=BrainRuntime.PYTHON,
            version="0.1",
            status=BrainStatus.IDLE,
        )
        caps = analyzer.analyze(record)
        assert "chat" in caps
        assert "local_inference" in caps
        assert "local" in caps
        assert "cli" in caps
        assert "python_runtime" in caps

    def test_anthropic_cloud_brain(self, analyzer: BrainCapabilityAnalyzer) -> None:
        record = BrainRecord(
            id="a1",
            display_name="Claude",
            brain_type=BrainType.CLOUD_API,
            vendor=BrainVendor.ANTHROPIC,
            runtime=BrainRuntime.CLOUD,
            version="3.5",
            status=BrainStatus.CONNECTED,
        )
        caps = analyzer.analyze(record)
        assert "chat" in caps
        assert "tool_use" in caps
        assert "extended_thinking" in caps

    def test_local_cli_brain(self, analyzer: BrainCapabilityAnalyzer) -> None:
        record = BrainRecord(
            id="l1",
            display_name="Local CLI",
            brain_type=BrainType.LOCAL_CLI,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.NATIVE,
            version="1",
            status=BrainStatus.CONNECTED,
        )
        caps = analyzer.analyze(record)
        assert "local" in caps
        assert "cli" in caps
        assert "code_generation" in caps
        assert "file_editing" in caps
        assert "terminal_access" in caps
        assert "native" in caps

    def test_mcp_server_brain(self, analyzer: BrainCapabilityAnalyzer) -> None:
        record = BrainRecord(
            id="m1",
            display_name="MCP Svr",
            brain_type=BrainType.MCP_SERVER,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.NODE,
            version="1",
            status=BrainStatus.CONNECTED,
        )
        caps = analyzer.analyze(record)
        assert "mcp" in caps
        assert "tool_provision" in caps
        assert "resource_access" in caps
        assert "node_runtime" in caps

    def test_orchestrator_brain(self, analyzer: BrainCapabilityAnalyzer) -> None:
        record = BrainRecord(
            id="or1",
            display_name="Orch",
            brain_type=BrainType.ORCHESTRATOR,
            vendor=BrainVendor.HERMES,
            runtime=BrainRuntime.PYTHON,
            version="1",
            status=BrainStatus.CONNECTED,
        )
        caps = analyzer.analyze(record)
        assert "orchestrator" in caps
        assert "multi_agent" in caps
        assert "planning" in caps
        assert "delegation" in caps
        assert "plugin_system" in caps
        assert "tool_use" in caps

    def test_supported_models_as_capabilities(
        self,
        analyzer: BrainCapabilityAnalyzer,
    ) -> None:
        record = BrainRecord(
            id="sm1",
            display_name="Models",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.CONNECTED,
            supported_models=("gpt-4", "claude-3"),
        )
        caps = analyzer.analyze(record)
        assert "model:gpt-4" in caps
        assert "model:claude-3" in caps

    def test_supported_tools_as_capabilities(
        self,
        analyzer: BrainCapabilityAnalyzer,
    ) -> None:
        record = BrainRecord(
            id="st1",
            display_name="Tools",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.CONNECTED,
            supported_tools=("code_interpreter", "web_search"),
        )
        caps = analyzer.analyze(record)
        assert "tool:code_interpreter" in caps
        assert "tool:web_search" in caps

    def test_deduplication(self, analyzer: BrainCapabilityAnalyzer) -> None:
        """Chat capability should appear only once even if derived from
        multiple sources (vendor + type + explicit)."""
        record = BrainRecord(
            id="d1",
            display_name="Dedup",
            brain_type=BrainType.LOCAL_CLI,
            vendor=BrainVendor.OPENAI,
            runtime=BrainRuntime.PYTHON,
            version="1",
            status=BrainStatus.CONNECTED,
            capabilities=("chat",),  # explicit
        )
        caps = analyzer.analyze(record)
        # "chat" from vendor + explicit capabilities
        assert caps.count("chat") == 1

    def test_result_is_sorted(self, analyzer: BrainCapabilityAnalyzer) -> None:
        record = BrainRecord(
            id="s1",
            display_name="Sorted",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.CONNECTED,
            capabilities=("zeta", "alpha", "beta"),
        )
        caps = analyzer.analyze(record)
        assert caps == tuple(sorted(caps))

    def test_unknown_vendor_returns_empty_vendor_caps(
        self,
        analyzer: BrainCapabilityAnalyzer,
    ) -> None:
        record = BrainRecord(
            id="u1",
            display_name="Unknown",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.CONNECTED,
        )
        caps = analyzer.analyze(record)
        assert "custom" in caps  # from brain_type.CUSTOM
        # no vendor-specific caps for CUSTOM


# ═══════════════════════════════════════════════════════════════════════
# has_capability()
# ═══════════════════════════════════════════════════════════════════════


class TestBrainCapabilityAnalyzerHasCapability:
    """has_capability() — boolean check for a single capability."""

    def test_has_capability_true(self, analyzer: BrainCapabilityAnalyzer) -> None:
        record = BrainRecord(
            id="h1",
            display_name="Has",
            brain_type=BrainType.CLOUD_API,
            vendor=BrainVendor.OPENAI,
            runtime=BrainRuntime.CLOUD,
            version="1",
            status=BrainStatus.CONNECTED,
        )
        assert analyzer.has_capability(record, "vision") is True

    def test_has_capability_false(self, analyzer: BrainCapabilityAnalyzer) -> None:
        record = BrainRecord(
            id="h2",
            display_name="No",
            brain_type=BrainType.LOCAL_CLI,
            vendor=BrainVendor.OLLAMA,
            runtime=BrainRuntime.PYTHON,
            version="1",
            status=BrainStatus.CONNECTED,
        )
        assert analyzer.has_capability(record, "vision") is False

    def test_has_capability_custom(self, analyzer: BrainCapabilityAnalyzer) -> None:
        record = BrainRecord(
            id="h3",
            display_name="Custom",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.CONNECTED,
            capabilities=("custom_cap_x",),
        )
        assert analyzer.has_capability(record, "custom_cap_x") is True


# ═══════════════════════════════════════════════════════════════════════
# match_capabilities()
# ═══════════════════════════════════════════════════════════════════════


class TestBrainCapabilityAnalyzerMatchCapabilities:
    """match_capabilities() — filter brains by required capabilities."""

    def test_match_require_all(self, analyzer: BrainCapabilityAnalyzer) -> None:
        records = [
            BrainRecord(
                id="r1",
                display_name="O",
                brain_type=BrainType.CLOUD_API,
                vendor=BrainVendor.OPENAI,
                runtime=BrainRuntime.CLOUD,
                version="1",
                status=BrainStatus.CONNECTED,
            ),
            BrainRecord(
                id="r2",
                display_name="L",
                brain_type=BrainType.LOCAL_CLI,
                vendor=BrainVendor.OLLAMA,
                runtime=BrainRuntime.PYTHON,
                version="1",
                status=BrainStatus.CONNECTED,
            ),
        ]
        matched = analyzer.match_capabilities(
            records,
            required={"chat", "cloud"},
            require_all=True,
        )
        assert len(matched) == 1
        assert matched[0].id == "r1"

    def test_match_require_any(self, analyzer: BrainCapabilityAnalyzer) -> None:
        records = [
            BrainRecord(
                id="r1",
                display_name="O",
                brain_type=BrainType.CLOUD_API,
                vendor=BrainVendor.OPENAI,
                runtime=BrainRuntime.CLOUD,
                version="1",
                status=BrainStatus.CONNECTED,
            ),
            BrainRecord(
                id="r2",
                display_name="L",
                brain_type=BrainType.LOCAL_CLI,
                vendor=BrainVendor.OLLAMA,
                runtime=BrainRuntime.PYTHON,
                version="1",
                status=BrainStatus.CONNECTED,
            ),
        ]
        matched = analyzer.match_capabilities(
            records,
            required={"vision", "local_inference"},
            require_all=False,
        )
        assert len(matched) == 2

    def test_match_empty_required(self, analyzer: BrainCapabilityAnalyzer) -> None:
        records = [
            BrainRecord(
                id="e1",
                display_name="E",
                brain_type=BrainType.CUSTOM,
                vendor=BrainVendor.CUSTOM,
                runtime=BrainRuntime.UNKNOWN,
                version="1",
                status=BrainStatus.CONNECTED,
            )
        ]
        matched = analyzer.match_capabilities(records, required=set())
        assert len(matched) == 1

    def test_match_no_results(self, analyzer: BrainCapabilityAnalyzer) -> None:
        records = [
            BrainRecord(
                id="n1",
                display_name="N",
                brain_type=BrainType.CUSTOM,
                vendor=BrainVendor.CUSTOM,
                runtime=BrainRuntime.UNKNOWN,
                version="1",
                status=BrainStatus.CONNECTED,
            )
        ]
        matched = analyzer.match_capabilities(
            records,
            required={"super_rare_capability"},
        )
        assert matched == []

    def test_match_empty_record_list(self, analyzer: BrainCapabilityAnalyzer) -> None:
        matched = analyzer.match_capabilities([], required={"chat"})
        assert matched == []


# ═══════════════════════════════════════════════════════════════════════
# Partial capability queries
# ═══════════════════════════════════════════════════════════════════════


class TestBrainCapabilityAnalyzerPartialQueries:
    """get_vendor_capabilities, get_type_capabilities, get_runtime_capabilities."""

    def test_get_vendor_capabilities_known(
        self,
        analyzer: BrainCapabilityAnalyzer,
    ) -> None:
        caps = analyzer.get_vendor_capabilities(BrainVendor.GROQ)
        assert "chat" in caps
        assert "streaming" in caps
        assert "fast_inference" in caps

    def test_get_vendor_capabilities_unknown(
        self,
        analyzer: BrainCapabilityAnalyzer,
    ) -> None:
        caps = analyzer.get_vendor_capabilities(BrainVendor.CUSTOM)
        assert caps == ()

    def test_get_type_capabilities_known(
        self,
        analyzer: BrainCapabilityAnalyzer,
    ) -> None:
        caps = analyzer.get_type_capabilities(BrainType.MCP_SERVER)
        assert "mcp" in caps
        assert "tool_provision" in caps

    def test_get_type_capabilities_custom(
        self,
        analyzer: BrainCapabilityAnalyzer,
    ) -> None:
        caps = analyzer.get_type_capabilities(BrainType.CUSTOM)
        assert caps == ("custom",)

    def test_get_runtime_capabilities_known(
        self,
        analyzer: BrainCapabilityAnalyzer,
    ) -> None:
        caps = analyzer.get_runtime_capabilities(BrainRuntime.GO)
        assert caps == ("go_runtime",)

    def test_get_runtime_capabilities_unknown(
        self,
        analyzer: BrainCapabilityAnalyzer,
    ) -> None:
        caps = analyzer.get_runtime_capabilities(BrainRuntime.UNKNOWN)
        assert caps == ()
