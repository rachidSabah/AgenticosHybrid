"""Tests for MCP Version Manager."""

import pytest

from agentic_os.core.mcp.version import (
    RECOMMENDED_PROTOCOL_VERSION,
    MCPVersionManager,
    ServerVersionInfo,
)


@pytest.fixture
def version_manager():
    return MCPVersionManager()


class TestMCPVersionManagerRegistration:
    def test_register_version(self, version_manager) -> None:
        info = ServerVersionInfo(
            server_id="srv1",
            protocol_version="2024-11-05",
            server_version="1.0.0",
        )
        version_manager.register_version("srv1", info)
        assert version_manager.get_version("srv1") is info

    def test_register_multiple_servers(self, version_manager) -> None:
        info1 = ServerVersionInfo(server_id="srv1", protocol_version="2024-11-05")
        info2 = ServerVersionInfo(server_id="srv2", protocol_version="2025-03-26")
        version_manager.register_version("srv1", info1)
        version_manager.register_version("srv2", info2)
        assert len(version_manager.list_versions()) == 2

    def test_get_version_not_found(self, version_manager) -> None:
        assert version_manager.get_version("nonexistent") is None

    def test_remove_version(self, version_manager) -> None:
        info = ServerVersionInfo(server_id="srv1")
        version_manager.register_version("srv1", info)
        version_manager.remove_version("srv1")
        assert version_manager.get_version("srv1") is None

    def test_remove_nonexistent(self, version_manager) -> None:
        version_manager.remove_version("nonexistent")

    def test_update_version(self, version_manager) -> None:
        info = ServerVersionInfo(server_id="srv1", protocol_version="2024-11-05")
        version_manager.register_version("srv1", info)
        version_manager.update_version("srv1", server_version="2.0.0")
        updated = version_manager.get_version("srv1")
        assert updated is not None
        assert updated.server_version == "2.0.0"

    def test_update_nonexistent(self, version_manager) -> None:
        version_manager.update_version("nonexistent", server_version="1.0.0")

    def test_clear(self, version_manager) -> None:
        version_manager.register_version("srv1", ServerVersionInfo(server_id="srv1"))
        version_manager.clear()
        assert len(version_manager.list_versions()) == 0


class TestMCPVersionManagerCompatibility:
    def test_check_no_version_info(self, version_manager) -> None:
        result = version_manager.check_compatibility("nonexistent")
        assert not result.compatible
        assert "No version info" in result.reason

    def test_check_no_protocol_version(self, version_manager) -> None:
        info = ServerVersionInfo(server_id="srv1")
        version_manager.register_version("srv1", info)
        result = version_manager.check_compatibility("srv1")
        assert not result.compatible

    def test_check_supported_version(self, version_manager) -> None:
        info = ServerVersionInfo(server_id="srv1", protocol_version="2024-11-05")
        version_manager.register_version("srv1", info)
        result = version_manager.check_compatibility("srv1")
        assert result.compatible
        assert result.protocol_version == "2024-11-05"

    def test_check_unsupported_version(self, version_manager) -> None:
        info = ServerVersionInfo(server_id="srv1", protocol_version="2023-01-01")
        version_manager.register_version("srv1", info)
        result = version_manager.check_compatibility("srv1")
        assert not result.compatible
        assert "not supported" in result.reason

    def test_negotiate_version_exact_match(self, version_manager) -> None:
        result = version_manager.negotiate_version("2024-11-05")
        assert result == "2024-11-05"

    def test_negotiate_version_newer(self, version_manager) -> None:
        result = version_manager.negotiate_version("2026-01-01")
        assert result is not None

    def test_negotiate_version_older(self, version_manager) -> None:
        result = version_manager.negotiate_version("2023-01-01")
        assert result is None

    def test_get_protocol_matrix(self, version_manager) -> None:
        info = ServerVersionInfo(server_id="srv1", protocol_version="2024-11-05")
        version_manager.register_version("srv1", info)
        matrix = version_manager.get_protocol_compatibility_matrix()
        assert "supported_versions" in matrix
        assert matrix["recommended_version"] == RECOMMENDED_PROTOCOL_VERSION
        assert "srv1" in matrix["servers"]
        assert matrix["servers"]["srv1"]["compatible"]

    def test_list_versions(self, version_manager) -> None:
        info = ServerVersionInfo(server_id="srv1", server_version="1.0.0")
        version_manager.register_version("srv1", info)
        versions = version_manager.list_versions()
        assert "srv1" in versions
        assert versions["srv1"].server_version == "1.0.0"
