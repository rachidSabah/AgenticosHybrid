"""Tests for MCP Prompt Registry."""

import pytest

from agentic_os.core.mcp.prompt_registry import (
    PROMPT_CATEGORIES,
    MCPPromptRegistry,
    PromptArgument,
    PromptDefinition,
)


@pytest.fixture
def prompt_registry():
    return MCPPromptRegistry()


@pytest.fixture
def sample_prompt():
    return PromptDefinition(
        name="review-code",
        server_id="srv1",
        description="Review code for best practices",
        template="Please review this {{language}} code:\n\n{{code}}",
        arguments=[
            PromptArgument(name="language", description="Programming language", required=True),
            PromptArgument(name="code", description="Source code", required=True),
        ],
        categories=["code_review"],
        tags=["review", "code-quality"],
    )


class TestMCPPromptRegistryRegistration:
    def test_register_prompt(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        assert len(prompt_registry.list_prompts()) == 1

    def test_register_duplicate(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        prompt_registry.register(sample_prompt)
        assert len(prompt_registry.list_prompts()) == 1

    def test_unregister_prompt(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        assert prompt_registry.unregister("srv1", "review-code")
        assert len(prompt_registry.list_prompts()) == 0

    def test_unregister_nonexistent(self, prompt_registry) -> None:
        assert not prompt_registry.unregister("srv1", "nonexistent")

    def test_get_prompt(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        prompt = prompt_registry.get_prompt("srv1", "review-code")
        assert prompt is not None
        assert prompt.name == "review-code"

    def test_get_prompt_not_found(self, prompt_registry) -> None:
        assert prompt_registry.get_prompt("srv1", "nonexistent") is None

    def test_get_server_prompts(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        p2 = PromptDefinition(
            name="generate-docs",
            server_id="srv1",
            description="Generate documentation",
            template="Generate docs for {{module}}",
            arguments=[PromptArgument(name="module", description="Module name", required=True)],
        )
        prompt_registry.register(p2)
        prompts = prompt_registry.get_server_prompts("srv1")
        assert len(prompts) == 2

    def test_clear_server(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        prompt_registry.clear_server("srv1")
        assert len(prompt_registry.list_prompts()) == 0

    def test_clear(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        prompt_registry.clear()
        assert len(prompt_registry.list_prompts()) == 0


class TestMCPPromptRegistrySearch:
    def test_find_by_category(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        results = prompt_registry.find_by_category("code_review")
        assert len(results) == 1

    def test_find_by_category_none(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        results = prompt_registry.find_by_category("testing")
        assert len(results) == 0

    def test_find_by_tag(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        results = prompt_registry.find_by_tag("review")
        assert len(results) == 1

    def test_search_by_name(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        results = prompt_registry.search_prompts("review")
        assert len(results) == 1

    def test_search_by_description(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        results = prompt_registry.search_prompts("best practices")
        assert len(results) == 1

    def test_search_no_match(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        results = prompt_registry.search_prompts("zzznonexistent")
        assert len(results) == 0


class TestMCPPromptRegistryLifecycle:
    def test_enable_disable_prompt(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        prompt_registry.disable_prompt("srv1", "review-code")
        assert not prompt_registry.get_prompt("srv1", "review-code").enabled
        prompt_registry.enable_prompt("srv1", "review-code")
        assert prompt_registry.get_prompt("srv1", "review-code").enabled

    def test_get_enabled_prompts(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        p2 = PromptDefinition(
            name="disabled-prompt",
            server_id="srv1",
            description="Disabled",
            template="disabled",
            enabled=False,
        )
        prompt_registry.register(p2)
        enabled = prompt_registry.get_enabled_prompts("srv1")
        assert len(enabled) == 1
        assert enabled[0].name == "review-code"

    def test_get_stats(self, prompt_registry, sample_prompt) -> None:
        prompt_registry.register(sample_prompt)
        stats = prompt_registry.get_stats()
        assert stats["total_prompts"] == 1
        assert stats["total_servers"] == 1

    def test_prompt_argument_defaults(self) -> None:
        arg = PromptArgument(name="optional_arg", description="An optional arg")
        assert not arg.required
        assert arg.default is None

    def test_prompt_argument_required(self) -> None:
        arg = PromptArgument(name="required_arg", description="Required", required=True)
        assert arg.required


class TestMCPPromptRegistryConstants:
    def test_prompt_categories_defined(self) -> None:
        assert "generic" in PROMPT_CATEGORIES
        assert "code_review" in PROMPT_CATEGORIES
        assert "documentation" in PROMPT_CATEGORIES
        assert "testing" in PROMPT_CATEGORIES
