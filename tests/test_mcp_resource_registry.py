"""Tests for MCP Resource Registry."""

import pytest

from agentic_os.core.mcp.resource_registry import (
    RESOURCE_CONTENT_TYPES,
    MCPResourceRegistry,
    ResourceDefinition,
)


@pytest.fixture
def resource_registry():
    return MCPResourceRegistry()


@pytest.fixture
def sample_resource():
    return ResourceDefinition(
        uri="file:///data/doc.md",
        server_id="srv1",
        name="document",
        description="A markdown document",
        mime_type="text/markdown",
        tags=["docs", "markdown"],
    )


class TestMCPResourceRegistryRegistration:
    def test_register_resource(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        assert len(resource_registry.list_resources()) == 1

    def test_register_duplicate(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        resource_registry.register(sample_resource)
        assert len(resource_registry.list_resources()) == 1

    def test_unregister_resource(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        assert resource_registry.unregister("srv1", "file:///data/doc.md")
        assert len(resource_registry.list_resources()) == 0

    def test_unregister_nonexistent(self, resource_registry) -> None:
        assert not resource_registry.unregister("srv1", "nonexistent")

    def test_get_resource(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        resource = resource_registry.get_resource("srv1", "file:///data/doc.md")
        assert resource is not None
        assert resource.name == "document"

    def test_get_resource_not_found(self, resource_registry) -> None:
        assert resource_registry.get_resource("srv1", "nonexistent") is None

    def test_get_server_resources(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        res2 = ResourceDefinition(
            uri="file:///data/doc2.md",
            server_id="srv1",
            name="document2",
            description="Another doc",
        )
        resource_registry.register(res2)
        resources = resource_registry.get_server_resources("srv1")
        assert len(resources) == 2

    def test_clear_server(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        resource_registry.clear_server("srv1")
        assert len(resource_registry.list_resources()) == 0

    def test_clear(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        resource_registry.clear()
        assert len(resource_registry.list_resources()) == 0


class TestMCPResourceRegistrySearch:
    def test_find_by_mime_type(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        results = resource_registry.find_by_mime_type("text/markdown")
        assert len(results) == 1

    def test_find_by_mime_type_none(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        results = resource_registry.find_by_mime_type("application/json")
        assert len(results) == 0

    def test_find_by_tag(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        results = resource_registry.find_by_tag("docs")
        assert len(results) == 1

    def test_search_resources_by_name(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        results = resource_registry.search_resources("document")
        assert len(results) == 1

    def test_search_resources_by_uri(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        results = resource_registry.search_resources("doc.md")
        assert len(results) == 1

    def test_search_no_match(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        results = resource_registry.search_resources("zzznonexistent")
        assert len(results) == 0


class TestMCPResourceRegistryLifecycle:
    def test_enable_disable(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        resource_registry.disable_resource("srv1", "file:///data/doc.md")
        assert not resource_registry.get_resource("srv1", "file:///data/doc.md").enabled
        resource_registry.enable_resource("srv1", "file:///data/doc.md")
        assert resource_registry.get_resource("srv1", "file:///data/doc.md").enabled

    def test_get_enabled_resources(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        disabled = ResourceDefinition(
            uri="file:///data/disabled.txt",
            server_id="srv1",
            name="disabled",
            description="Disabled resource",
            enabled=False,
        )
        resource_registry.register(disabled)
        enabled = resource_registry.get_enabled_resources("srv1")
        assert len(enabled) == 1

    def test_get_stats(self, resource_registry, sample_resource) -> None:
        resource_registry.register(sample_resource)
        stats = resource_registry.get_stats()
        assert stats["total_resources"] == 1
        assert stats["total_servers"] == 1


class TestMCPResourceRegistryConstants:
    def test_content_types_defined(self) -> None:
        assert "text/plain" in RESOURCE_CONTENT_TYPES
        assert "application/json" in RESOURCE_CONTENT_TYPES
        assert "text/markdown" in RESOURCE_CONTENT_TYPES
