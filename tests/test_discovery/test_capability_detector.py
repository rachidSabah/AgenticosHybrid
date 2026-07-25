"""Tests for CapabilityDetector (Phase 6.1)."""

from __future__ import annotations

import pytest

from agentic_os.core.discovery.local.capability_detector import CapabilityDetector
from agentic_os.domain.discovery import AgentCapability


class TestCapabilityDetector:
    @pytest.fixture
    def detector(self) -> CapabilityDetector:
        return CapabilityDetector()

    def test_detect_hermes(self, detector: CapabilityDetector) -> None:
        caps = detector.detect("hermes")
        assert AgentCapability.CODE_GENERATION in caps
        assert AgentCapability.CHAT in caps
        assert AgentCapability.MCP in caps
        assert AgentCapability.FILE_OPS in caps
        assert AgentCapability.TERMINAL_OPS in caps
        assert AgentCapability.REASONING in caps

    def test_detect_ollama(self, detector: CapabilityDetector) -> None:
        caps = detector.detect("ollama")
        assert AgentCapability.CHAT in caps
        assert AgentCapability.EMBEDDINGS in caps
        assert AgentCapability.REASONING in caps
        assert AgentCapability.CODE_GENERATION not in caps

    def test_detect_python(self, detector: CapabilityDetector) -> None:
        caps = detector.detect("python")
        assert AgentCapability.CODE_GENERATION in caps
        assert AgentCapability.TESTING in caps
        assert AgentCapability.REASONING in caps
        assert AgentCapability.FILE_OPS in caps

    def test_detect_docker(self, detector: CapabilityDetector) -> None:
        caps = detector.detect("docker")
        assert AgentCapability.CUSTOM in caps

    def test_detect_unknown_tool_returns_empty(self, detector: CapabilityDetector) -> None:
        caps = detector.detect("completely-unknown-tool")
        assert caps == ()

    def test_detect_case_sensitive(self, detector: CapabilityDetector) -> None:
        caps = detector.detect("HERMES")
        assert caps == ()

    def test_detect_codex(self, detector: CapabilityDetector) -> None:
        caps = detector.detect("codex")
        assert AgentCapability.CODE_GENERATION in caps
        assert AgentCapability.TESTING in caps
        assert AgentCapability.REASONING in caps
        assert AgentCapability.TERMINAL_OPS in caps

    def test_detect_claude_code(self, detector: CapabilityDetector) -> None:
        caps = detector.detect("claude-code")
        assert AgentCapability.CODE_GENERATION in caps
        assert AgentCapability.CHAT in caps
        assert AgentCapability.MCP in caps

    def test_detect_git(self, detector: CapabilityDetector) -> None:
        caps = detector.detect("git")
        assert AgentCapability.FILE_OPS in caps
        assert AgentCapability.CUSTOM in caps
        assert AgentCapability.CHAT not in caps

    def test_detect_node(self, detector: CapabilityDetector) -> None:
        caps = detector.detect("node")
        assert AgentCapability.CODE_GENERATION in caps
        assert AgentCapability.TESTING in caps

    def test_detect_vscode_cli(self, detector: CapabilityDetector) -> None:
        caps = detector.detect("vscode-cli")
        assert AgentCapability.CODE_GENERATION in caps
        assert AgentCapability.CODE_REVIEW in caps
        assert AgentCapability.CHAT in caps
        assert AgentCapability.TERMINAL_OPS in caps
        assert AgentCapability.FILE_OPS in caps

    def test_detect_gemini_cli(self, detector: CapabilityDetector) -> None:
        caps = detector.detect("gemini-cli")
        assert AgentCapability.CODE_GENERATION in caps
        assert AgentCapability.CHAT in caps
        assert AgentCapability.REASONING in caps

    def test_detect_batch(self, detector: CapabilityDetector) -> None:
        tools = [("hermes", "1.0"), ("ollama", "0.1"), ("unknown", "")]
        results = detector.detect_batch(tools)
        assert len(results) == 3
        hermes_caps = [r for r in results if r[0] == "hermes"][0][1]
        assert AgentCapability.CHAT in hermes_caps
        unknown_caps = [r for r in results if r[0] == "unknown"][0][1]
        assert unknown_caps == ()
