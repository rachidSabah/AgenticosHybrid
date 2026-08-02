"""Tests for RuntimeBridge — runtime connectors for local CLI AI brains."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_os.core.brains.runtime_bridge import (
    AiderConnector,
    BrainConnector,
    ClaudeCodeConnector,
    CodexConnector,
    ContinueConnector,
    GeminiCliConnector,
    HermesConnector,
    OpenCodeConnector,
    RuntimeBridge,
    RuntimeInfo,
    _GenericCliConnector,
)
from agentic_os.domain.brains import (
    BrainRecord,
    BrainRuntime,
    BrainStatus,
    BrainType,
    BrainVendor,
    WorkspaceInfo,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def bridge() -> RuntimeBridge:
    return RuntimeBridge()


@pytest.fixture
def mock_connector() -> MagicMock:
    conn = MagicMock(spec=BrainConnector)
    conn.tool_type = "mock-tool"
    conn.display_name = "Mock Tool"
    conn.vendor = BrainVendor.CUSTOM
    conn.detect = AsyncMock(
        return_value=RuntimeInfo(
            tool_type="mock-tool",
            display_name="Mock Tool",
            vendor=BrainVendor.CUSTOM,
            installed=True,
            status=BrainStatus.DISCOVERED,
        )
    )
    conn.query_status = AsyncMock(return_value={"status": "running"})
    conn.query_workspace = AsyncMock(return_value=WorkspaceInfo(workspace_path="/mock"))
    conn.query_sessions = AsyncMock(return_value=[{"id": "s1"}])
    conn.to_brain_record = AsyncMock(
        return_value=BrainRecord(
            id="mock-id",
            display_name="Mock Tool",
            brain_type=BrainType.LOCAL_CLI,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1.0",
            status=BrainStatus.DISCOVERED,
        )
    )
    return conn


# ═══════════════════════════════════════════════════════════════════════════════
# RuntimeBridge — initialization
# ═══════════════════════════════════════════════════════════════════════════════


class TestRuntimeBridgeInit:
    def test_registers_default_connectors(self, bridge: RuntimeBridge) -> None:
        assert bridge.get_connector("claude-code") is not None
        assert bridge.get_connector("hermes") is not None
        assert bridge.get_connector("gemini-cli") is not None
        assert bridge.get_connector("codex") is not None
        assert bridge.get_connector("opencode") is not None
        assert bridge.get_connector("aider") is not None
        assert bridge.get_connector("continue") is not None

    def test_default_connectors_are_correct_types(self, bridge: RuntimeBridge) -> None:
        assert isinstance(bridge.get_connector("claude-code"), ClaudeCodeConnector)
        assert isinstance(bridge.get_connector("hermes"), HermesConnector)
        assert isinstance(bridge.get_connector("gemini-cli"), GeminiCliConnector)
        assert isinstance(bridge.get_connector("codex"), CodexConnector)
        assert isinstance(bridge.get_connector("opencode"), OpenCodeConnector)
        assert isinstance(bridge.get_connector("aider"), AiderConnector)
        assert isinstance(bridge.get_connector("continue"), ContinueConnector)

    def test_default_vendors(self, bridge: RuntimeBridge) -> None:
        assert bridge.get_connector("claude-code").vendor == BrainVendor.CLAUDE_CODE
        assert bridge.get_connector("hermes").vendor == BrainVendor.HERMES
        assert bridge.get_connector("gemini-cli").vendor == BrainVendor.GEMINI_CLI
        assert bridge.get_connector("codex").vendor == BrainVendor.CODEX
        assert bridge.get_connector("opencode").vendor == BrainVendor.OPENCODE
        assert bridge.get_connector("aider").vendor == BrainVendor.AIDER
        assert bridge.get_connector("continue").vendor == BrainVendor.CONTINUE


# ═══════════════════════════════════════════════════════════════════════════════
# RuntimeBridge — connector management
# ═══════════════════════════════════════════════════════════════════════════════


class TestRuntimeBridgeConnectorManagement:
    def test_register_connector(self, bridge: RuntimeBridge, mock_connector: MagicMock) -> None:
        bridge.register_connector(mock_connector)
        assert bridge.get_connector("mock-tool") is mock_connector

    def test_register_overwrites(self, bridge: RuntimeBridge, mock_connector: MagicMock) -> None:
        bridge.register_connector(mock_connector)
        second = MagicMock(spec=BrainConnector)
        second.tool_type = "mock-tool"
        bridge.register_connector(second)
        assert bridge.get_connector("mock-tool") is second

    def test_get_connector_returns_none_for_unknown(self, bridge: RuntimeBridge) -> None:
        assert bridge.get_connector("nonexistent") is None

    def test_list_connectors_returns_all(self, bridge: RuntimeBridge) -> None:
        conns = bridge.list_connectors()
        assert len(conns) == 7

    def test_list_tool_types(self, bridge: RuntimeBridge) -> None:
        types = bridge.list_tool_types()
        assert "claude-code" in types
        assert "hermes" in types
        assert "codex" in types
        assert len(types) == 7


# ═══════════════════════════════════════════════════════════════════════════════
# RuntimeBridge — detection
# ═══════════════════════════════════════════════════════════════════════════════


class TestRuntimeBridgeDetection:
    async def test_detect_all_runs_on_all_connectors(self, bridge: RuntimeBridge) -> None:
        results = await bridge.detect_all(use_cache=False)
        assert len(results) == 7

    async def test_detect_all_uses_cache(
        self, bridge: RuntimeBridge, mock_connector: MagicMock
    ) -> None:
        bridge.register_connector(mock_connector)

        # First call populates cache
        await bridge.detect_all(use_cache=True)
        assert mock_connector.detect.call_count == 1

        # Second call should use cache
        await bridge.detect_all(use_cache=True)
        assert mock_connector.detect.call_count == 1  # Not called again

    async def test_detect_all_bypasses_cache(
        self, bridge: RuntimeBridge, mock_connector: MagicMock
    ) -> None:
        bridge.register_connector(mock_connector)

        await bridge.detect_all(use_cache=True)
        await bridge.detect_all(use_cache=False)
        assert mock_connector.detect.call_count == 2

    async def test_detect_all_handles_connector_error(self, bridge: RuntimeBridge) -> None:
        failing = MagicMock(spec=BrainConnector)
        failing.tool_type = "failing"
        failing.display_name = "Failing"
        failing.vendor = BrainVendor.CUSTOM
        failing.detect = AsyncMock(side_effect=RuntimeError("detect fail"))
        bridge.register_connector(failing)

        results = await bridge.detect_all(use_cache=False)
        # Should return a RuntimeInfo with installed=False for failing connector
        failing_results = [r for r in results if r.tool_type == "failing"]
        assert len(failing_results) == 1
        assert failing_results[0].installed is False
        assert failing_results[0].status == BrainStatus.REMOVED

    async def test_detect_one_returns_info(self, bridge: RuntimeBridge) -> None:
        info = await bridge.detect_one("hermes")
        assert info is not None
        assert info.tool_type == "hermes"

    async def test_detect_one_unknown_connector(self, bridge: RuntimeBridge) -> None:
        info = await bridge.detect_one("nonexistent")
        assert info is None

    async def test_detect_one_updates_cache(
        self, bridge: RuntimeBridge, mock_connector: MagicMock
    ) -> None:
        bridge.register_connector(mock_connector)
        await bridge.detect_one("mock-tool")
        # Verify it's cached
        async with bridge._lock:
            assert "mock-tool" in bridge._cache

    async def test_detect_one_handles_error(self, bridge: RuntimeBridge) -> None:
        failing = MagicMock(spec=BrainConnector)
        failing.tool_type = "failing"
        failing.detect = AsyncMock(side_effect=RuntimeError("fail"))
        bridge.register_connector(failing)

        info = await bridge.detect_one("failing")
        assert info is None

    async def test_clear_cache(self, bridge: RuntimeBridge, mock_connector: MagicMock) -> None:
        bridge.register_connector(mock_connector)
        await bridge.detect_all(use_cache=True)
        await bridge.clear_cache()
        async with bridge._lock:
            assert bridge._cache == {}


# ═══════════════════════════════════════════════════════════════════════════════
# RuntimeBridge — status, workspace, sessions
# ═══════════════════════════════════════════════════════════════════════════════


class TestRuntimeBridgeQueries:
    async def test_query_status(self, bridge: RuntimeBridge, mock_connector: MagicMock) -> None:
        bridge.register_connector(mock_connector)
        status = await bridge.query_status("mock-tool")
        assert status == {"status": "running"}

    async def test_query_status_unknown_connector(self, bridge: RuntimeBridge) -> None:
        status = await bridge.query_status("nonexistent")
        assert status["status"] == "unknown"
        assert "error" in status

    async def test_query_status_handles_error(self, bridge: RuntimeBridge) -> None:
        failing = MagicMock(spec=BrainConnector)
        failing.tool_type = "failing"
        failing.query_status = AsyncMock(side_effect=RuntimeError("status fail"))
        bridge.register_connector(failing)

        status = await bridge.query_status("failing")
        assert status["status"] == "error"

    async def test_query_workspace(self, bridge: RuntimeBridge, mock_connector: MagicMock) -> None:
        bridge.register_connector(mock_connector)
        ws = await bridge.query_workspace("mock-tool")
        assert ws.workspace_path == "/mock"

    async def test_query_workspace_unknown_connector(self, bridge: RuntimeBridge) -> None:
        ws = await bridge.query_workspace("nonexistent")
        assert isinstance(ws, WorkspaceInfo)

    async def test_query_sessions(self, bridge: RuntimeBridge, mock_connector: MagicMock) -> None:
        bridge.register_connector(mock_connector)
        sessions = await bridge.query_sessions("mock-tool")
        assert sessions == [{"id": "s1"}]

    async def test_query_sessions_unknown_connector(self, bridge: RuntimeBridge) -> None:
        sessions = await bridge.query_sessions("nonexistent")
        assert sessions == []


# ═══════════════════════════════════════════════════════════════════════════════
# RuntimeBridge — BrainRecord conversion
# ═══════════════════════════════════════════════════════════════════════════════


class TestRuntimeBridgeConversion:
    async def test_to_brain_record(self, bridge: RuntimeBridge) -> None:
        record = await bridge.to_brain_record("hermes")
        assert record is not None
        assert isinstance(record, BrainRecord)
        assert record.display_name == "Hermes Agent"
        assert record.vendor == BrainVendor.HERMES
        assert record.brain_type == BrainType.LOCAL_CLI

    async def test_to_brain_record_unknown_connector(self, bridge: RuntimeBridge) -> None:
        record = await bridge.to_brain_record("nonexistent")
        assert record is None

    async def test_to_brain_record_runs_detection_when_no_cache(
        self, bridge: RuntimeBridge, mock_connector: MagicMock
    ) -> None:
        bridge.register_connector(mock_connector)
        record = await bridge.to_brain_record("mock-tool")
        assert record is not None
        assert mock_connector.detect.called
        assert mock_connector.to_brain_record.called

    async def test_to_brain_record_uses_cache(
        self, bridge: RuntimeBridge, mock_connector: MagicMock
    ) -> None:
        bridge.register_connector(mock_connector)
        # Pre-cache
        async with bridge._lock:
            bridge._cache["mock-tool"] = RuntimeInfo(
                tool_type="mock-tool",
                display_name="Mock Tool",
                vendor=BrainVendor.CUSTOM,
                installed=True,
            )
        record = await bridge.to_brain_record("mock-tool")
        assert record is not None
        # detect_one should NOT be called because cache exists
        assert mock_connector.detect.call_count == 0

    async def test_to_brain_records(self, bridge: RuntimeBridge) -> None:
        records = await bridge.to_brain_records()
        assert len(records) == 7  # One per default connector
        for r in records:
            assert isinstance(r, BrainRecord)

    async def test_to_brain_records_with_custom_connector(
        self, bridge: RuntimeBridge, mock_connector: MagicMock
    ) -> None:
        bridge.register_connector(mock_connector)
        records = await bridge.to_brain_records()
        assert len(records) == 8
        mock_tool_records = [r for r in records if r.display_name == "Mock Tool"]
        assert len(mock_tool_records) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# BrainConnector — abstract interface
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainConnectorInterface:
    async def test_detect_raises_not_implemented(self) -> None:
        conn = BrainConnector()
        with pytest.raises(NotImplementedError):
            await conn.detect()

    async def test_query_status_raises_not_implemented(self) -> None:
        conn = BrainConnector()
        with pytest.raises(NotImplementedError):
            await conn.query_status()

    async def test_query_workspace_raises_not_implemented(self) -> None:
        conn = BrainConnector()
        with pytest.raises(NotImplementedError):
            await conn.query_workspace()

    async def test_query_sessions_raises_not_implemented(self) -> None:
        conn = BrainConnector()
        with pytest.raises(NotImplementedError):
            await conn.query_sessions()

    async def test_to_brain_record_raises_not_implemented(self) -> None:
        conn = BrainConnector()
        with pytest.raises(NotImplementedError):
            await conn.to_brain_record(
                RuntimeInfo(
                    tool_type="test",
                    display_name="Test",
                    vendor=BrainVendor.CUSTOM,
                )
            )


# ═══════════════════════════════════════════════════════════════════════════════
# _GenericCliConnector
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenericCliConnector:
    @patch("agentic_os.core.brains.runtime_bridge.shutil.which")
    async def test_detect_installed(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "/usr/bin/hermes"
        connector = _GenericCliConnector(
            tool_type="hermes",
            display_name="Hermes Agent",
            vendor=BrainVendor.HERMES,
            exe_name="hermes",
        )

        info = await connector.detect()
        assert info.installed is True
        assert info.executable == "/usr/bin/hermes"
        assert info.status == BrainStatus.DISCOVERED

    @patch("agentic_os.core.brains.runtime_bridge.shutil.which")
    async def test_detect_not_installed(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        connector = _GenericCliConnector(
            tool_type="hermes",
            display_name="Hermes Agent",
            vendor=BrainVendor.HERMES,
            exe_name="hermes",
        )

        info = await connector.detect()
        assert info.installed is False
        assert info.executable == ""
        assert info.status == BrainStatus.REMOVED

    async def test_to_brain_record_python_runtime(self) -> None:
        connector = _GenericCliConnector(
            tool_type="hermes",
            display_name="Hermes Agent",
            vendor=BrainVendor.HERMES,
            exe_name="hermes",
        )
        info = RuntimeInfo(
            tool_type="hermes",
            display_name="Hermes Agent",
            vendor=BrainVendor.HERMES,
            installed=True,
            executable="/usr/bin/hermes",
            version="1.0.0",
        )
        record = await connector.to_brain_record(info)
        assert isinstance(record, BrainRecord)
        assert record.runtime == BrainRuntime.PYTHON
        assert record.health == 100.0

    async def test_to_brain_record_node_runtime(self) -> None:
        connector = _GenericCliConnector(
            tool_type="continue",
            display_name="Continue",
            vendor=BrainVendor.CONTINUE,
            exe_name="continue",
        )
        info = RuntimeInfo(
            tool_type="continue",
            display_name="Continue",
            vendor=BrainVendor.CONTINUE,
            installed=True,
        )
        record = await connector.to_brain_record(info)
        assert record.runtime == BrainRuntime.UNKNOWN

    async def test_to_brain_record_native_runtime(self) -> None:
        connector = _GenericCliConnector(
            tool_type="codex",
            display_name="Codex CLI",
            vendor=BrainVendor.CODEX,
            exe_name="codex",
        )
        info = RuntimeInfo(
            tool_type="codex",
            display_name="Codex CLI",
            vendor=BrainVendor.CODEX,
            installed=True,
        )
        record = await connector.to_brain_record(info)
        assert record.runtime == BrainRuntime.NATIVE

    async def test_to_brain_record_not_installed_zero_health(self) -> None:
        connector = _GenericCliConnector(
            tool_type="hermes",
            display_name="Hermes Agent",
            vendor=BrainVendor.HERMES,
            exe_name="hermes",
        )
        info = RuntimeInfo(
            tool_type="hermes",
            display_name="Hermes Agent",
            vendor=BrainVendor.HERMES,
            installed=False,
        )
        record = await connector.to_brain_record(info)
        assert record.health == 0.0
        assert record.status == BrainStatus.DISCOVERED

    async def test_query_status_returns_unknown(self) -> None:
        connector = _GenericCliConnector(
            tool_type="test", display_name="Test", vendor=BrainVendor.CUSTOM, exe_name="test"
        )
        status = await connector.query_status()
        assert status == {"status": "unknown"}

    async def test_query_workspace_returns_cwd(self) -> None:
        connector = _GenericCliConnector(
            tool_type="test", display_name="Test", vendor=BrainVendor.CUSTOM, exe_name="test"
        )
        ws = await connector.query_workspace()
        assert hasattr(ws, "workspace_path")

    async def test_query_sessions_returns_empty(self) -> None:
        connector = _GenericCliConnector(
            tool_type="test", display_name="Test", vendor=BrainVendor.CUSTOM, exe_name="test"
        )
        sessions = await connector.query_sessions()
        assert sessions == []

    async def test_to_brain_record_includes_version_in_capabilities(self) -> None:
        connector = _GenericCliConnector(
            tool_type="test", display_name="Test", vendor=BrainVendor.CUSTOM, exe_name="test"
        )
        info = RuntimeInfo(
            tool_type="test",
            display_name="Test",
            vendor=BrainVendor.CUSTOM,
            installed=True,
            executable="/usr/bin/test",
            version="2.0.0",
            capabilities=("cli:test", "version:2.0.0"),
        )
        record = await connector.to_brain_record(info)
        assert "cli:test" in record.capabilities

    async def test_to_brain_record_has_valid_id(self) -> None:
        connector = _GenericCliConnector(
            tool_type="test", display_name="Test", vendor=BrainVendor.CUSTOM, exe_name="test"
        )
        info = RuntimeInfo(
            tool_type="test",
            display_name="Test",
            vendor=BrainVendor.CUSTOM,
            installed=True,
        )
        record = await connector.to_brain_record(info)
        assert len(record.id) == 12
