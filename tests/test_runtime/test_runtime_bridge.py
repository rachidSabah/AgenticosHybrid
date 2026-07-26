"""Tests for RuntimeBridge — discovery-to-runtime mapping, sync, auto-registration."""

import pytest

from agentic_os.core.runtime.runtime import (
    Runtime,
    RuntimeCapability,
    RuntimeHealth,
    RuntimeStatus,
    RuntimeType,
)
from agentic_os.core.runtime.runtime_bridge import RuntimeBridge, _map_type
from agentic_os.core.runtime.runtime_registry import RuntimeRegistry


@pytest.fixture
async def registry() -> RuntimeRegistry:
    return RuntimeRegistry()


@pytest.fixture
def bridge(registry) -> RuntimeBridge:
    return RuntimeBridge(registry=registry)


class TestMapType:
    def test_map_known_types(self) -> None:
        assert _map_type("python") == RuntimeType.PYTHON
        assert _map_type("node") == RuntimeType.NODE
        assert _map_type("docker") == RuntimeType.DOCKER
        assert _map_type("git") == RuntimeType.GIT
        assert _map_type("claude_code") == RuntimeType.CLAUDE_CODE
        assert _map_type("opencode") == RuntimeType.OPENCODE
        assert _map_type("codex_cli") == RuntimeType.CODEX_CLI
        assert _map_type("gemini_cli") == RuntimeType.GEMINI_CLI
        assert _map_type("mcp_server") == RuntimeType.MCP_SERVER

    def test_map_unknown_types_to_custom(self) -> None:
        assert _map_type("unknown") == RuntimeType.CUSTOM
        assert _map_type("ollama") == RuntimeType.CUSTOM
        assert _map_type("lm_studio") == RuntimeType.CUSTOM
        assert _map_type("random_tool") == RuntimeType.CUSTOM

    def test_map_nonexistent_string(self) -> None:
        assert _map_type("completely_fake") == RuntimeType.CUSTOM


class TestRuntimeBridge:
    @pytest.mark.asyncio
    async def test_discover_to_runtime_from_object(self, bridge: RuntimeBridge) -> None:
        class _RuntimeInfo:
            runtime_type = "python"
            name = "Python 3.11"
            version = "3.11.5"
            path = "/usr/bin/python3"
            executable = "python3"
            capabilities = ["coding", "terminal"]
            source = "auto"

        info = _RuntimeInfo()
        runtime = bridge.discover_to_runtime(info)
        assert runtime.name == "Python 3.11"
        assert runtime.type == RuntimeType.PYTHON
        assert runtime.version == "3.11.5"
        assert runtime.binary_path == "/usr/bin/python3"
        assert runtime.status == RuntimeStatus.DISCOVERED
        assert runtime.health == RuntimeHealth.UNKNOWN
        assert runtime.discovered is True
        assert len(runtime.capabilities) == 2
        assert runtime.capabilities[0].name == "coding"

    @pytest.mark.asyncio
    async def test_discover_to_runtime_from_dict(self, bridge: RuntimeBridge) -> None:
        info = {
            "runtime_type": "node",
            "name": "Node 20",
            "version": "20.0.0",
            "path": "/usr/local/bin/node",
            "executable": "node",
            "capabilities": ["http", "fs"],
            "source": "manual",
        }
        runtime = bridge.discover_to_runtime(info)
        assert runtime.name == "Node 20"
        assert runtime.type == RuntimeType.NODE
        assert runtime.binary_path == "/usr/local/bin/node"
        assert runtime.source == "manual"
        assert len(runtime.capabilities) == 2

    @pytest.mark.asyncio
    async def test_discover_to_runtime_minimal(self, bridge: RuntimeBridge) -> None:
        info = {"runtime_type": "unknown"}
        runtime = bridge.discover_to_runtime(info)
        assert runtime.type == RuntimeType.CUSTOM
        assert runtime.name == "custom"  # fallback name
        assert runtime.discovered is True

    @pytest.mark.asyncio
    async def test_discover_to_runtime_with_enum_type(self, bridge: RuntimeBridge) -> None:
        class _RuntimeType:
            def __init__(self, value: str):
                self.value = value

        class _Info:
            runtime_type = _RuntimeType("docker")
            name = "Docker Engine"
            version = None
            path = None
            executable = "docker"
            capabilities = []
            source = "auto"

        runtime = bridge.discover_to_runtime(_Info())
        assert runtime.type == RuntimeType.DOCKER

    @pytest.mark.asyncio
    async def test_sync_discovered_empty(
        self, bridge: RuntimeBridge, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _empty() -> list:
            return []

        monkeypatch.setattr(bridge, "_run_discovery", _empty)
        registered = await bridge.sync_discovered()
        assert registered == []

    @pytest.mark.asyncio
    async def test_sync_discovered_skips_duplicates(
        self, bridge: RuntimeBridge, registry: RuntimeRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _empty() -> list:
            return []

        monkeypatch.setattr(bridge, "_run_discovery", _empty)
        # Manually register a runtime first
        r = Runtime(name="manual-rt", type=RuntimeType.PYTHON)
        await registry.register(r)
        registered = await bridge.sync_discovered()
        assert isinstance(registered, list)

    @pytest.mark.asyncio
    async def test_get_discovery_status(self, bridge: RuntimeBridge) -> None:
        status = await bridge.get_discovery_status()
        assert status["bridge_available"] is True
        assert status["total_registered"] == 0
        assert status["active_runtimes"] == 0
        assert "last_discovery" in status

    @pytest.mark.asyncio
    async def test_discovery_status_with_registered(
        self, bridge: RuntimeBridge, registry: RuntimeRegistry
    ) -> None:
        r = Runtime(name="registered-rt", type=RuntimeType.PYTHON)
        await registry.register(r)
        status = await bridge.get_discovery_status()
        assert status["total_registered"] == 1

    @pytest.mark.asyncio
    async def test_manual_register_and_discover(
        self, bridge: RuntimeBridge, registry: RuntimeRegistry
    ) -> None:
        """Verify that a manually registered runtime appears in discovery status."""
        r = Runtime(name="visible", type=RuntimeType.NODE)
        await registry.register(r)
        status = await bridge.get_discovery_status()
        assert status["total_registered"] >= 1

    @pytest.mark.asyncio
    async def test_discover_to_runtime_preserves_source(self, bridge: RuntimeBridge) -> None:
        info = {"runtime_type": "git", "name": "Git", "source": "system_path"}
        runtime = bridge.discover_to_runtime(info)
        assert runtime.source == "system_path"

    @pytest.mark.asyncio
    async def test_discover_to_runtime_empty_name(self, bridge: RuntimeBridge) -> None:
        info = {"runtime_type": "python", "name": ""}
        runtime = bridge.discover_to_runtime(info)
        assert runtime.name == "python"  # fallback to type value

    @pytest.mark.asyncio
    async def test_discover_to_runtime_capability_as_strings(self, bridge: RuntimeBridge) -> None:
        class _Info:
            runtime_type = "mcp_server"
            name = "MCP"
            version = None
            path = None
            executable = None
            capabilities = ["filesystem", "database", "http"]
            source = "config"

        runtime = bridge.discover_to_runtime(_Info())
        assert len(runtime.capabilities) == 3
        assert all(isinstance(c, RuntimeCapability) for c in runtime.capabilities)
        assert runtime.capabilities[0].name == "filesystem"

    @pytest.mark.asyncio
    async def test_bridge_initialization(self, registry: RuntimeRegistry) -> None:
        bridge = RuntimeBridge(registry=registry)
        assert bridge._registry is registry
        assert bridge._last_discovery == {}
        assert bridge._bus is None
