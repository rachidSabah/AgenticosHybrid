"""Tests for BrainCatalog — maps tool-types to brain classes and provides
a catalogue of known cloud AI vendors and their capabilities."""

from __future__ import annotations

from copy import deepcopy

import pytest

from agentic_os.core.brains import catalog as catalog_module
from agentic_os.core.brains.catalog import BrainCatalog, ToolMapping, VendorInfo
from agentic_os.domain.brains import BrainRecord, BrainRuntime, BrainStatus, BrainType, BrainVendor

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def catalog() -> BrainCatalog:
    return BrainCatalog()


@pytest.fixture
def saved_mappings() -> dict[str, ToolMapping]:
    return deepcopy(catalog_module._BUILTIN_TOOL_MAPPINGS)


@pytest.fixture
def saved_vendors() -> dict[BrainVendor, VendorInfo]:
    return deepcopy(catalog_module._CLOUD_VENDOR_CATALOG)


@pytest.fixture
def isolated_catalog(
    saved_mappings: dict[str, ToolMapping],
    saved_vendors: dict[BrainVendor, VendorInfo],
) -> BrainCatalog:
    """Restore global state after mutation tests."""
    yield BrainCatalog()
    catalog_module._BUILTIN_TOOL_MAPPINGS.clear()
    catalog_module._BUILTIN_TOOL_MAPPINGS.update(saved_mappings)
    catalog_module._CLOUD_VENDOR_CATALOG.clear()
    catalog_module._CLOUD_VENDOR_CATALOG.update(saved_vendors)


@pytest.fixture
def count_mappings() -> int:
    return len(catalog_module._BUILTIN_TOOL_MAPPINGS)


@pytest.fixture
def count_vendors() -> int:
    return len(catalog_module._CLOUD_VENDOR_CATALOG)


# ═══════════════════════════════════════════════════════════════════════════════
# Tool-type mappings
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainCatalogToolMappings:
    def test_get_mapping_returns_tool_mapping(self, catalog: BrainCatalog) -> None:
        mapping = catalog.get_mapping("hermes")
        assert mapping is not None
        assert isinstance(mapping, ToolMapping)
        assert mapping.tool_type == "hermes"
        assert mapping.brain_type == BrainType.LOCAL_CLI
        assert mapping.default_vendor == BrainVendor.HERMES
        assert mapping.default_runtime == BrainRuntime.PYTHON

    def test_get_mapping_all_known(self, catalog: BrainCatalog) -> None:
        known = ["claude-code", "hermes", "gemini-cli", "codex", "opencode", "aider", "continue"]
        for tool_type in known:
            mapping = catalog.get_mapping(tool_type)
            assert mapping is not None, f"Expected mapping for {tool_type}"
            assert mapping.tool_type == tool_type

    def test_get_mapping_returns_none_for_unknown(self, catalog: BrainCatalog) -> None:
        mapping = catalog.get_mapping("nonexistent-tool")
        assert mapping is None

    def test_get_mapping_claude_code(self, catalog: BrainCatalog) -> None:
        mapping = catalog.get_mapping("claude-code")
        assert mapping is not None
        assert mapping.default_vendor == BrainVendor.CLAUDE_CODE
        assert mapping.default_runtime == BrainRuntime.NATIVE
        assert "Claude Code" in mapping.description

    def test_get_mapping_gemini_cli(self, catalog: BrainCatalog) -> None:
        mapping = catalog.get_mapping("gemini-cli")
        assert mapping is not None
        assert mapping.default_vendor == BrainVendor.GEMINI_CLI
        assert mapping.default_runtime == BrainRuntime.NATIVE

    def test_get_mapping_continue(self, catalog: BrainCatalog) -> None:
        mapping = catalog.get_mapping("continue")
        assert mapping is not None
        assert mapping.default_runtime == BrainRuntime.NODE
        assert "Continue" in mapping.description

    def test_register_mapping_adds_new(self, isolated_catalog: BrainCatalog) -> None:
        new_mapping = ToolMapping(
            tool_type="my-custom-tool",
            brain_type=BrainType.CUSTOM,
            default_vendor=BrainVendor.CUSTOM,
            default_runtime=BrainRuntime.UNKNOWN,
            description="My custom tool",
        )
        isolated_catalog.register_mapping(new_mapping)
        assert isolated_catalog.get_mapping("my-custom-tool") is new_mapping

    def test_register_mapping_overwrites_existing(self, isolated_catalog: BrainCatalog) -> None:
        new_mapping = ToolMapping(
            tool_type="hermes",
            brain_type=BrainType.CUSTOM,
            default_vendor=BrainVendor.CUSTOM,
            default_runtime=BrainRuntime.UNKNOWN,
        )
        isolated_catalog.register_mapping(new_mapping)
        mapping = isolated_catalog.get_mapping("hermes")
        assert mapping.brain_type == BrainType.CUSTOM  # Overwritten

    def test_list_mappings_returns_all(self, catalog: BrainCatalog, count_mappings: int) -> None:
        mappings = catalog.list_mappings()
        assert len(mappings) == count_mappings
        tool_types = {m.tool_type for m in mappings}
        expected = {"claude-code", "hermes", "gemini-cli", "codex", "opencode", "aider", "continue"}
        assert expected.issubset(tool_types)

    def test_resolve_returns_classification(self, catalog: BrainCatalog) -> None:
        result = catalog.resolve("hermes")
        assert result is not None
        btype, vendor, runtime = result
        assert btype == BrainType.LOCAL_CLI
        assert vendor == BrainVendor.HERMES
        assert runtime == BrainRuntime.PYTHON

    def test_resolve_returns_none_for_unknown(self, catalog: BrainCatalog) -> None:
        result = catalog.resolve("unknown-tool")
        assert result is None

    def test_resolve_all_known(self, catalog: BrainCatalog) -> None:
        known = ["claude-code", "hermes", "gemini-cli", "codex", "opencode", "aider", "continue"]
        for t in known:
            result = catalog.resolve(t)
            assert result is not None, f"Expected resolve to succeed for {t}"


# ═══════════════════════════════════════════════════════════════════════════════
# Cloud vendor catalogue
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainCatalogVendors:
    def test_get_vendor_returns_vendor_info(self, catalog: BrainCatalog) -> None:
        info = catalog.get_vendor(BrainVendor.OPENAI)
        assert info is not None
        assert isinstance(info, VendorInfo)
        assert info.name == "OpenAI"
        assert info.vendor == BrainVendor.OPENAI
        assert info.base_url == "https://api.openai.com/v1"

    def test_get_vendor_all_known(self, catalog: BrainCatalog) -> None:
        known = [
            BrainVendor.OPENAI,
            BrainVendor.ANTHROPIC,
            BrainVendor.GOOGLE,
            BrainVendor.MISTRAL,
            BrainVendor.GROQ,
            BrainVendor.AZURE,
            BrainVendor.AWS,
            BrainVendor.VERTEX,
            BrainVendor.OPENROUTER,
            BrainVendor.OLLAMA,
            BrainVendor.DEEPSEEK,
        ]
        for v in known:
            info = catalog.get_vendor(v)
            assert info is not None, f"Expected vendor info for {v}"

    def test_get_vendor_returns_none_for_unknown(self, catalog: BrainCatalog) -> None:
        info = catalog.get_vendor(BrainVendor.CUSTOM)
        assert info is None

    def test_list_vendors_returns_all(self, catalog: BrainCatalog, count_vendors: int) -> None:
        vendors = catalog.list_vendors()
        assert len(vendors) == count_vendors
        names = {v.name for v in vendors}
        assert "OpenAI" in names
        assert "Anthropic" in names
        assert "DeepSeek" in names

    def test_list_vendor_names(self, catalog: BrainCatalog, count_vendors: int) -> None:
        names = catalog.list_vendor_names()
        assert len(names) == count_vendors
        assert "OpenAI" in names
        assert "Ollama" in names

    def test_register_vendor_adds_entry(self, isolated_catalog: BrainCatalog) -> None:
        new_vendor = VendorInfo(
            name="Test Vendor",
            vendor=BrainVendor.CUSTOM,
            api_type="custom",
            base_url="https://test.ai/v1",
            known_models=("test-model",),
            supported_capabilities=("chat",),
        )
        isolated_catalog.register_vendor(new_vendor)
        info = isolated_catalog.get_vendor(BrainVendor.CUSTOM)
        assert info is not None
        assert info.name == "Test Vendor"

    def test_register_vendor_overwrites(self, isolated_catalog: BrainCatalog) -> None:
        modified = VendorInfo(
            name="Modified OpenAI",
            vendor=BrainVendor.OPENAI,
            api_type="custom",
            base_url="https://custom.openai.com",
        )
        isolated_catalog.register_vendor(modified)
        info = isolated_catalog.get_vendor(BrainVendor.OPENAI)
        assert info.name == "Modified OpenAI"
        assert info.base_url == "https://custom.openai.com"

    def test_get_supported_models(self, catalog: BrainCatalog) -> None:
        models = catalog.get_supported_models(BrainVendor.OPENAI)
        assert len(models) > 0
        assert "gpt-4o" in models

    def test_get_supported_models_unknown_vendor(self, catalog: BrainCatalog) -> None:
        models = catalog.get_supported_models(BrainVendor.CUSTOM)
        assert models == ()

    def test_get_supported_capabilities(self, catalog: BrainCatalog) -> None:
        caps = catalog.get_supported_capabilities(BrainVendor.ANTHROPIC)
        assert "chat" in caps
        assert "vision" in caps
        assert "tool_use" in caps

    def test_get_supported_capabilities_unknown_vendor(self, catalog: BrainCatalog) -> None:
        caps = catalog.get_supported_capabilities(BrainVendor.CUSTOM)
        assert caps == ()

    def test_vendor_info_defaults(self) -> None:
        info = VendorInfo(name="Test", vendor=BrainVendor.CUSTOM)
        assert info.default_runtime == BrainRuntime.CLOUD
        assert info.api_type == "cloud"
        assert info.base_url == ""
        assert info.known_models == ()
        assert info.supported_capabilities == ()


# ═══════════════════════════════════════════════════════════════════════════════
# Factory: create_from_dict
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainCatalogCreateFromDict:
    def test_create_from_dict_with_all_fields(self, catalog: BrainCatalog) -> None:
        data = {
            "id": "custom-id",
            "display_name": "Custom Brain",
            "vendor": "hermes",
            "brain_type": "local_cli",
            "runtime": "python",
            "status": "connected",
            "version": "1.0.0",
            "health": 95.0,
            "capabilities": ["chat", "code"],
            "supported_models": ["gpt-4"],
            "memory_usage": 128.0,
            "cpu_usage": 10.0,
            "latency": 5.0,
            "throughput": 100.0,
            "workspace": "/home/user",
            "current_tasks": 3,
            "queue_depth": 1,
            "connection_state": "connected",
            "uptime": 3600.0,
            "tags": ["dev"],
            "metadata": {"key": "val"},
        }
        record = catalog.create_from_dict(data)
        assert isinstance(record, BrainRecord)
        assert record.id == "custom-id"
        assert record.display_name == "Custom Brain"
        assert record.vendor == BrainVendor.HERMES
        assert record.brain_type == BrainType.LOCAL_CLI
        assert record.runtime == BrainRuntime.PYTHON
        assert record.status == BrainStatus.CONNECTED
        assert record.health == 95.0
        assert record.capabilities == ("chat", "code")
        assert record.supported_models == ("gpt-4",)
        assert record.memory_usage == 128.0
        assert record.cpu_usage == 10.0
        assert record.latency == 5.0
        assert record.throughput == 100.0
        assert record.workspace == "/home/user"
        assert record.current_tasks == 3
        assert record.queue_depth == 1
        assert record.connection_state == "connected"
        assert record.uptime == 3600.0
        assert record.tags == ("dev",)
        assert record.metadata == {"key": "val"}

    def test_create_from_dict_minimal(self, catalog: BrainCatalog) -> None:
        data = {"vendor": "hermes"}
        record = catalog.create_from_dict(data)
        assert record.vendor == BrainVendor.HERMES
        assert record.brain_type == BrainType.LOCAL_CLI
        assert record.status == BrainStatus.DISCOVERED
        assert record.health == 1.0  # default health
        assert record.runtime == BrainRuntime.UNKNOWN

    def test_create_from_dict_empty_dict(self, catalog: BrainCatalog) -> None:
        record = catalog.create_from_dict({})
        assert record.vendor == BrainVendor.CUSTOM
        assert record.brain_type == BrainType.LOCAL_CLI
        assert record.status == BrainStatus.DISCOVERED
        assert record.health == 1.0
        assert record.id != ""

    def test_create_from_dict_invalid_vendor(self, catalog: BrainCatalog) -> None:
        data = {"vendor": "nonexistent-vendor"}
        record = catalog.create_from_dict(data)
        assert record.vendor == BrainVendor.CUSTOM

    def test_create_from_dict_invalid_brain_type(self, catalog: BrainCatalog) -> None:
        data = {"vendor": "custom", "brain_type": "invalid_type"}
        record = catalog.create_from_dict(data)
        assert record.brain_type == BrainType.LOCAL_CLI

    def test_create_from_dict_invalid_runtime(self, catalog: BrainCatalog) -> None:
        data = {"vendor": "custom", "runtime": "invalid_runtime"}
        record = catalog.create_from_dict(data)
        assert record.runtime == BrainRuntime.UNKNOWN

    def test_create_from_dict_invalid_status(self, catalog: BrainCatalog) -> None:
        data = {"vendor": "custom", "status": "invalid_status"}
        record = catalog.create_from_dict(data)
        assert record.status == BrainStatus.DISCOVERED

    def test_create_from_dict_uses_name_as_fallback(self, catalog: BrainCatalog) -> None:
        data = {"name": "My Brain", "vendor": "hermes"}
        record = catalog.create_from_dict(data)
        assert record.display_name == "My Brain"

    def test_capabilities_from_supported_tools(self, catalog: BrainCatalog) -> None:
        data = {"vendor": "hermes", "supported_tools": ["bash", "file"]}
        record = catalog.create_from_dict(data)
        assert record.capabilities == ("bash", "file")

    def test_create_from_dict_health_default(self, catalog: BrainCatalog) -> None:
        record = catalog.create_from_dict({"vendor": "hermes"})
        assert record.health == 1.0

    def test_create_from_dict_generates_uuid_id(self, catalog: BrainCatalog) -> None:
        record = catalog.create_from_dict({"vendor": "hermes"})
        assert record.id != ""
        assert isinstance(record.id, str)
