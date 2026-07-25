"""Tests for BrainDiscoveryBridge — subscribes to local agent discovery events
and converts them into BrainRecord instances."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agentic_os.core.brains.bridge import BrainDiscoveryBridge
from agentic_os.domain.brains import BrainRecord, BrainStatus, BrainType, BrainVendor
from agentic_os.domain.events import EventEnvelope, Topic

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def event_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.subscribe = AsyncMock(return_value="sub-1")
    bus.unsubscribe = AsyncMock()
    return bus


@pytest.fixture
def on_brain() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def bridge() -> BrainDiscoveryBridge:
    return BrainDiscoveryBridge()


# ── Helper ───────────────────────────────────────────────────────────────────


def make_event(topic: Topic, payload: dict | None = None) -> EventEnvelope:
    return EventEnvelope(
        type=topic.value,
        source="test",
        topic=topic.value,
        payload=payload or {},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Lifecycle — start / stop
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainDiscoveryBridgeStart:
    async def test_start_subscribes_to_all_four_topics(
        self, bridge: BrainDiscoveryBridge, event_bus: AsyncMock, on_brain: AsyncMock
    ) -> None:
        await bridge.start(event_bus=event_bus, on_brain_registered=on_brain)
        assert bridge._started is True
        assert bridge._event_bus is event_bus
        assert bridge._on_brain is on_brain
        # Should subscribe to 4 topics
        assert event_bus.subscribe.call_count == 4
        assert len(bridge._subscriptions) == 4

    async def test_start_subscribes_to_expected_topics(
        self, bridge: BrainDiscoveryBridge, event_bus: AsyncMock
    ) -> None:
        await bridge.start(event_bus=event_bus)
        expected_topics = [
            Topic.AGENT_DISCOVERED.value,
            Topic.AGENT_REGISTERED.value,
            Topic.AGENT_UPDATED.value,
            Topic.AGENT_REMOVED.value,
        ]
        actual_topics = [call[0][0] for call in event_bus.subscribe.call_args_list]
        for t in expected_topics:
            assert t in actual_topics

    async def test_start_handles_subscription_error(
        self, bridge: BrainDiscoveryBridge, event_bus: AsyncMock
    ) -> None:
        event_bus.subscribe = AsyncMock(side_effect=RuntimeError("subscribe fail"))
        # Should not raise, should log error
        await bridge.start(event_bus=event_bus)
        assert bridge._started is True

    async def test_start_without_callback(
        self, bridge: BrainDiscoveryBridge, event_bus: AsyncMock
    ) -> None:
        await bridge.start(event_bus=event_bus)
        assert bridge._on_brain is None


class TestBrainDiscoveryBridgeStop:
    async def test_stop_unsubscribes_all(
        self, bridge: BrainDiscoveryBridge, event_bus: AsyncMock
    ) -> None:
        await bridge.start(event_bus=event_bus)
        await bridge.stop()
        assert bridge._started is False
        assert event_bus.unsubscribe.call_count == 4
        assert bridge._subscriptions == []

    async def test_stop_when_not_started_is_safe(self, bridge: BrainDiscoveryBridge) -> None:
        await bridge.stop()  # should not raise

    async def test_stop_twice_is_safe(
        self, bridge: BrainDiscoveryBridge, event_bus: AsyncMock
    ) -> None:
        await bridge.start(event_bus=event_bus)
        await bridge.stop()
        await bridge.stop()  # should not raise

    async def test_stop_handles_unsubscribe_error(
        self, bridge: BrainDiscoveryBridge, event_bus: AsyncMock
    ) -> None:
        event_bus.unsubscribe = AsyncMock(side_effect=RuntimeError("unsub fail"))
        await bridge.start(event_bus=event_bus)
        await bridge.stop()  # should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# Event handling
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainDiscoveryBridgeHandleEvent:
    async def test_handle_event_with_valid_payload_calls_on_brain(
        self, bridge: BrainDiscoveryBridge, event_bus: AsyncMock, on_brain: AsyncMock
    ) -> None:
        await bridge.start(event_bus=event_bus, on_brain_registered=on_brain)
        event = make_event(
            Topic.AGENT_DISCOVERED, {"id": "agent-1", "name": "Test Agent", "tool_type": "hermes"}
        )

        await bridge._handle_event(event)

        on_brain.assert_called_once()
        record = on_brain.call_args[0][0]
        assert isinstance(record, BrainRecord)
        assert record.id == "agent-1"
        assert record.display_name == "Test Agent"
        await bridge.stop()

    async def test_handle_event_with_missing_id_is_noop(
        self, bridge: BrainDiscoveryBridge, event_bus: AsyncMock, on_brain: AsyncMock
    ) -> None:
        await bridge.start(event_bus=event_bus, on_brain_registered=on_brain)
        event = make_event(Topic.AGENT_DISCOVERED, {"name": "No ID"})

        await bridge._handle_event(event)

        on_brain.assert_not_called()
        await bridge.stop()

    async def test_handle_event_with_none_payload_is_noop(
        self, bridge: BrainDiscoveryBridge, event_bus: AsyncMock, on_brain: AsyncMock
    ) -> None:
        await bridge.start(event_bus=event_bus, on_brain_registered=on_brain)
        event = make_event(Topic.AGENT_DISCOVERED, None)

        await bridge._handle_event(event)

        on_brain.assert_not_called()
        await bridge.stop()

    async def test_handle_event_no_callback(
        self, bridge: BrainDiscoveryBridge, event_bus: AsyncMock
    ) -> None:
        await bridge.start(event_bus=event_bus)
        event = make_event(Topic.AGENT_DISCOVERED, {"id": "agent-1", "tool_type": "hermes"})

        # Should not raise
        await bridge._handle_event(event)
        await bridge.stop()

    async def test_handle_event_exception_handling(
        self, bridge: BrainDiscoveryBridge, event_bus: AsyncMock
    ) -> None:
        await bridge.start(event_bus=event_bus)
        # Use valid envelope with payload that triggers missing 'id' key
        event = make_event(Topic.AGENT_DISCOVERED, {"tool_type": "hermes"})

        # Should not raise (caught by try/except)
        await bridge._handle_event(event)
        await bridge.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# Conversion: _convert
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainDiscoveryBridgeConvert:
    def test_convert_agent_discovered(self, bridge: BrainDiscoveryBridge) -> None:
        payload = {"id": "a1", "name": "Agent 1", "tool_type": "hermes"}
        record = bridge._convert(payload, Topic.AGENT_DISCOVERED.value)

        assert record is not None
        assert record.id == "a1"
        assert record.display_name == "Agent 1"
        assert record.status == BrainStatus.DISCOVERED
        assert record.vendor == BrainVendor.HERMES
        assert record.brain_type == BrainType.LOCAL_CLI

    def test_convert_agent_registered(self, bridge: BrainDiscoveryBridge) -> None:
        payload = {"id": "a2", "name": "Agent 2", "tool_type": "claude-code"}
        record = bridge._convert(payload, Topic.AGENT_REGISTERED.value)

        assert record is not None
        assert record.status == BrainStatus.REGISTERED
        assert record.vendor == BrainVendor.CLAUDE_CODE

    def test_convert_agent_removed(self, bridge: BrainDiscoveryBridge) -> None:
        payload = {"id": "a3", "name": "Agent 3", "tool_type": "opencode"}
        record = bridge._convert(payload, Topic.AGENT_REMOVED.value)

        assert record is not None
        assert record.status == BrainStatus.REMOVED
        assert record.vendor == BrainVendor.OPENCODE

    def test_convert_agent_updated(self, bridge: BrainDiscoveryBridge) -> None:
        payload = {"id": "a4", "name": "Agent 4", "tool_type": "codex"}
        record = bridge._convert(payload, Topic.AGENT_UPDATED.value)

        assert record is not None
        assert record.vendor == BrainVendor.CODEX
        assert record.brain_type == BrainType.LOCAL_CLI

    def test_convert_unknown_tool_type_returns_custom(self, bridge: BrainDiscoveryBridge) -> None:
        payload = {"id": "a5", "name": "Custom", "tool_type": "unknown-tool"}
        record = bridge._convert(payload, Topic.AGENT_DISCOVERED.value)

        assert record is not None
        assert record.vendor == BrainVendor.CUSTOM
        assert record.brain_type == BrainType.CUSTOM

    def test_convert_empty_tool_type_returns_none(self, bridge: BrainDiscoveryBridge) -> None:
        payload = {"id": "a6", "display_name": "No Tool Info", "tool_type": ""}
        record = bridge._convert(payload, Topic.AGENT_DISCOVERED.value)

        assert record is None

    def test_convert_missing_tool_type_returns_none(self, bridge: BrainDiscoveryBridge) -> None:
        payload = {"id": "a6b", "display_name": "No Tool Info"}
        record = bridge._convert(payload, Topic.AGENT_DISCOVERED.value)

        assert record is None

    def test_convert_with_all_fields(self, bridge: BrainDiscoveryBridge) -> None:
        payload = {
            "id": "a7",
            "name": "Full Agent",
            "tool_type": "hermes",
            "version": "2.0.0",
            "health_score": 95.0,
            "supported_models": ["gpt-4", "claude-3"],
            "supported_tools": ["bash", "file"],
            "capabilities": ["chat", "code"],
            "tags": ["local", "dev"],
            "memory_mb": 256.0,
            "cpu_percent": 12.5,
            "latency_ms": 5.0,
            "working_directory": "/home/user",
            "current_tasks": 3,
            "queue_depth": 1,
            "metadata": {"key": "val"},
            "discovered_at": "2025-01-01T00:00:00",
            "last_seen": "2025-01-01T00:00:01",
            "error_count": 0,
            "last_error": "",
        }
        record = bridge._convert(payload, Topic.AGENT_REGISTERED.value)

        assert record is not None
        assert record.id == "a7"
        assert record.display_name == "Full Agent"
        assert record.vendor == BrainVendor.HERMES
        assert record.version == "2.0.0"
        assert record.health == 95.0
        assert record.supported_models == ("gpt-4", "claude-3")
        assert record.supported_tools == ("bash", "file")
        assert record.capabilities == ("chat", "code")
        assert record.tags == ("local", "dev")
        assert record.memory_usage == 256.0
        assert record.cpu_usage == 12.5
        assert record.latency == 5.0
        assert record.workspace == "/home/user"
        assert record.current_tasks == 3
        assert record.queue_depth == 1
        assert record.metadata == {"key": "val"}
        assert record.error_count == 0

    def test_convert_uses_name_as_fallback_display_name(self, bridge: BrainDiscoveryBridge) -> None:
        payload = {"id": "a8", "name": "Named Agent", "tool_type": "hermes"}
        record = bridge._convert(payload, Topic.AGENT_DISCOVERED.value)
        assert record is not None
        assert record.display_name == "Named Agent"

    def test_convert_uses_tool_type_as_display_name_fallback(
        self, bridge: BrainDiscoveryBridge
    ) -> None:
        payload = {"id": "a9", "tool_type": "hermes"}
        record = bridge._convert(payload, Topic.AGENT_DISCOVERED.value)
        assert record is not None
        assert record.display_name == "hermes"

    def test_convert_generates_id_when_missing(self, bridge: BrainDiscoveryBridge) -> None:
        payload = {"tool_type": "hermes"}
        record = bridge._convert(payload, Topic.AGENT_DISCOVERED.value)
        assert record is not None
        assert len(record.id) == 12  # uuid4().hex[:12]


# ═══════════════════════════════════════════════════════════════════════════════
# Resolution helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainDiscoveryBridgeResolveVendor:
    def test_known_tool_types(self, bridge: BrainDiscoveryBridge) -> None:
        assert bridge._resolve_vendor("claude-code") == BrainVendor.CLAUDE_CODE
        assert bridge._resolve_vendor("hermes") == BrainVendor.HERMES
        assert bridge._resolve_vendor("gemini-cli") == BrainVendor.GEMINI_CLI
        assert bridge._resolve_vendor("codex") == BrainVendor.CODEX
        assert bridge._resolve_vendor("opencode") == BrainVendor.OPENCODE
        assert bridge._resolve_vendor("aider") == BrainVendor.AIDER
        assert bridge._resolve_vendor("continue") == BrainVendor.CONTINUE
        assert bridge._resolve_vendor("ollama") == BrainVendor.OLLAMA

    def test_case_insensitive(self, bridge: BrainDiscoveryBridge) -> None:
        assert bridge._resolve_vendor("Hermes") == BrainVendor.HERMES
        assert bridge._resolve_vendor("CLAUDE-CODE") == BrainVendor.CLAUDE_CODE

    def test_unknown_tool_type_returns_custom(self, bridge: BrainDiscoveryBridge) -> None:
        assert bridge._resolve_vendor("unknown") == BrainVendor.CUSTOM

    def test_resolve_gemini_alias(self, bridge: BrainDiscoveryBridge) -> None:
        assert bridge._resolve_vendor("gemini") == BrainVendor.GEMINI_CLI


class TestBrainDiscoveryBridgeResolveBrainType:
    def test_local_cli_tool_types(self, bridge: BrainDiscoveryBridge) -> None:
        assert bridge._resolve_brain_type("claude-code") == BrainType.LOCAL_CLI
        assert bridge._resolve_brain_type("hermes") == BrainType.LOCAL_CLI
        assert bridge._resolve_brain_type("opencode") == BrainType.LOCAL_CLI

    def test_ollama_maps_to_local_cli(self, bridge: BrainDiscoveryBridge) -> None:
        assert bridge._resolve_brain_type("ollama") == BrainType.LOCAL_CLI

    def test_lm_studio_maps_to_local_cli(self, bridge: BrainDiscoveryBridge) -> None:
        assert bridge._resolve_brain_type("lm-studio") == BrainType.LOCAL_CLI

    def test_vllm_maps_to_local_cli(self, bridge: BrainDiscoveryBridge) -> None:
        assert bridge._resolve_brain_type("vllm") == BrainType.LOCAL_CLI

    def test_unknown_tool_type_returns_custom(self, bridge: BrainDiscoveryBridge) -> None:
        assert bridge._resolve_brain_type("custom-tool") == BrainType.CUSTOM

    def test_case_insensitive(self, bridge: BrainDiscoveryBridge) -> None:
        assert bridge._resolve_brain_type("Hermes") == BrainType.LOCAL_CLI


class TestBrainDiscoveryBridgeResolveStatus:
    def test_status_from_payload_running(self, bridge: BrainDiscoveryBridge) -> None:
        status = bridge._resolve_status({"status": "running"}, Topic.AGENT_DISCOVERED.value)
        assert status == BrainStatus.CONNECTED

    def test_status_from_payload_idle(self, bridge: BrainDiscoveryBridge) -> None:
        status = bridge._resolve_status({"status": "idle"}, Topic.AGENT_DISCOVERED.value)
        assert status == BrainStatus.IDLE

    def test_status_from_payload_busy(self, bridge: BrainDiscoveryBridge) -> None:
        status = bridge._resolve_status({"status": "busy"}, Topic.AGENT_DISCOVERED.value)
        assert status == BrainStatus.BUSY

    def test_status_from_payload_stopped(self, bridge: BrainDiscoveryBridge) -> None:
        status = bridge._resolve_status({"status": "stopped"}, Topic.AGENT_DISCOVERED.value)
        assert status == BrainStatus.DISCONNECTED

    def test_status_from_payload_crashed(self, bridge: BrainDiscoveryBridge) -> None:
        status = bridge._resolve_status({"status": "crashed"}, Topic.AGENT_DISCOVERED.value)
        assert status == BrainStatus.FAILED

    def test_status_from_payload_degraded(self, bridge: BrainDiscoveryBridge) -> None:
        status = bridge._resolve_status({"status": "degraded"}, Topic.AGENT_DISCOVERED.value)
        assert status == BrainStatus.DEGRADED

    def test_status_from_payload_unknown(self, bridge: BrainDiscoveryBridge) -> None:
        status = bridge._resolve_status({"status": "unknown"}, Topic.AGENT_DISCOVERED.value)
        assert status == BrainStatus.DISCOVERED

    def test_status_fallback_to_removed_topic(self, bridge: BrainDiscoveryBridge) -> None:
        status = bridge._resolve_status({}, Topic.AGENT_REMOVED.value)
        assert status == BrainStatus.REMOVED

    def test_status_fallback_to_discovered_topic(self, bridge: BrainDiscoveryBridge) -> None:
        status = bridge._resolve_status({}, Topic.AGENT_DISCOVERED.value)
        assert status == BrainStatus.DISCOVERED

    def test_status_fallback_to_registered_topic(self, bridge: BrainDiscoveryBridge) -> None:
        status = bridge._resolve_status({}, Topic.AGENT_REGISTERED.value)
        assert status == BrainStatus.REGISTERED

    def test_status_default_when_no_match(self, bridge: BrainDiscoveryBridge) -> None:
        status = bridge._resolve_status({}, "unknown.topic")
        assert status == BrainStatus.DISCOVERED
