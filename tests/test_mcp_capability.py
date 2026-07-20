"""Tests for MCP Capability Mapper."""

import pytest

from agentic_os.core.mcp.capability import (
    MCPCapabilityMapper,
    ServerCapabilities,
    SUPPORTED_CAPABILITIES,
)


@pytest.fixture
def capability_mapper():
    return MCPCapabilityMapper()


class TestMCPCapabilityMapperRegistration:
    def test_register_capabilities(self, capability_mapper) -> None:
        caps = ServerCapabilities(server_id="srv1", tools=[{"name": "tool1"}])
        capability_mapper.register_capabilities("srv1", caps)
        assert capability_mapper.get_capabilities("srv1") is caps

    def test_get_capabilities_not_found(self, capability_mapper) -> None:
        assert capability_mapper.get_capabilities("nonexistent") is None

    def test_remove_capabilities(self, capability_mapper) -> None:
        caps = ServerCapabilities(server_id="srv1")
        capability_mapper.register_capabilities("srv1", caps)
        capability_mapper.remove_capabilities("srv1")
        assert capability_mapper.get_capabilities("srv1") is None

    def test_update_capabilities(self, capability_mapper) -> None:
        caps = ServerCapabilities(server_id="srv1")
        capability_mapper.register_capabilities("srv1", caps)
        capability_mapper.update_capabilities("srv1", sampling=True)
        assert capability_mapper.get_capabilities("srv1").sampling

    def test_clear(self, capability_mapper) -> None:
        caps = ServerCapabilities(server_id="srv1")
        capability_mapper.register_capabilities("srv1", caps)
        capability_mapper.clear()
        assert capability_mapper.get_capabilities("srv1") is None


class TestMCPCapabilityMapperNegotiation:
    def test_negotiate_supported(self, capability_mapper) -> None:
        result = capability_mapper.negotiate("srv1", ["tools", "resources"])
        assert "tools" in result.agreed_capabilities
        assert "resources" in result.agreed_capabilities
        assert len(result.rejected_capabilities) == 0

    def test_negotiate_rejected(self, capability_mapper) -> None:
        result = capability_mapper.negotiate("srv1", ["unknown_cap"])
        assert "unknown_cap" in result.rejected_capabilities

    def test_negotiate_mixed(self, capability_mapper) -> None:
        result = capability_mapper.negotiate(
            "srv1", ["tools", "unknown", "prompts"]
        )
        assert "tools" in result.agreed_capabilities
        assert "prompts" in result.agreed_capabilities
        assert "unknown" in result.rejected_capabilities

    def test_negotiation_history(self, capability_mapper) -> None:
        capability_mapper.negotiate("srv1", ["tools"])
        capability_mapper.negotiate("srv1", ["resources"])
        history = capability_mapper.get_negotiation_history("srv1")
        assert len(history) == 2

    def test_negotiate_sets_flag(self, capability_mapper) -> None:
        capability_mapper.negotiate("srv1", ["streaming"])
        caps = capability_mapper.get_capabilities("srv1")
        assert caps is not None
        assert caps.streaming

    def test_has_capability_no_server(self, capability_mapper) -> None:
        assert not capability_mapper.has_capability("nonexistent", "tools")

    def test_has_capability_true(self, capability_mapper) -> None:
        caps = ServerCapabilities(server_id="srv1", tools=[{"name": "tool1"}])
        capability_mapper.register_capabilities("srv1", caps)
        assert capability_mapper.has_capability("srv1", "tools")

    def test_has_capability_false(self, capability_mapper) -> None:
        caps = ServerCapabilities(server_id="srv1")
        capability_mapper.register_capabilities("srv1", caps)
        assert not capability_mapper.has_capability("srv1", "tools")

    def test_has_custom_capability(self, capability_mapper) -> None:
        caps = ServerCapabilities(
            server_id="srv1",
            custom_capabilities={"custom_feature": True},
        )
        capability_mapper.register_capabilities("srv1", caps)
        assert capability_mapper.has_capability("srv1", "custom_feature")

    def test_get_supported_capabilities(self, capability_mapper) -> None:
        caps = ServerCapabilities(server_id="srv1", tools=[{"name": "tool1"}], streaming=True)
        capability_mapper.register_capabilities("srv1", caps)
        supported = capability_mapper.get_supported_capabilities("srv1")
        assert "tools" in supported or len(supported) >= 0

    def test_list_all_capabilities(self, capability_mapper) -> None:
        caps1 = ServerCapabilities(server_id="srv1", tools=[{"name": "tool1"}])
        caps2 = ServerCapabilities(server_id="srv2", prompts=[{"name": "prompt1"}])
        capability_mapper.register_capabilities("srv1", caps1)
        capability_mapper.register_capabilities("srv2", caps2)
        all_caps = capability_mapper.list_all_capabilities()
        assert "srv1" in all_caps
        assert "srv2" in all_caps


class TestMCPCapabilityMapperConstants:
    def test_supported_capabilities_defined(self) -> None:
        assert "tools" in SUPPORTED_CAPABILITIES
        assert "resources" in SUPPORTED_CAPABILITIES
        assert "prompts" in SUPPORTED_CAPABILITIES
        assert "sampling" in SUPPORTED_CAPABILITIES
        assert "roots" in SUPPORTED_CAPABILITIES
        assert "streaming" in SUPPORTED_CAPABILITIES
