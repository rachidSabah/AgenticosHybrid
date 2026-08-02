"""
MCP Prompt Registry

Standalone registry for managing MCP prompt templates across all servers.
Supports prompt templates with arguments, categorized prompt discovery,
and prompt lifecycle management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("mcp.prompt_registry")


PROMPT_CATEGORIES: list[str] = [
    "generic",
    "code_review",
    "documentation",
    "testing",
    "debugging",
    "architecture",
    "security",
    "performance",
    "conversation",
    "transformation",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class PromptArgument:
    """An argument for a prompt template."""

    name: str
    description: str
    required: bool = False
    default: Any = None


@dataclass
class PromptDefinition:
    """A registered prompt definition."""

    name: str
    server_id: str
    description: str
    template: str
    arguments: list[PromptArgument] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    enabled: bool = True
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class MCPPromptRegistry:
    """Registry for MCP prompt definitions."""

    def __init__(self) -> None:
        self._prompts: dict[str, PromptDefinition] = {}
        self._server_prompts: dict[str, list[str]] = {}

    def register(self, prompt: PromptDefinition) -> None:
        key = f"{prompt.server_id}:{prompt.name}"
        self._prompts[key] = prompt
        if prompt.server_id not in self._server_prompts:
            self._server_prompts[prompt.server_id] = []
        if prompt.name not in self._server_prompts[prompt.server_id]:
            self._server_prompts[prompt.server_id].append(prompt.name)
        log.info(f"Registered prompt '{prompt.name}' for server {prompt.server_id}")

    def unregister(self, server_id: str, prompt_name: str) -> bool:
        key = f"{server_id}:{prompt_name}"
        if key in self._prompts:
            del self._prompts[key]
            server_prompts = self._server_prompts.get(server_id, [])
            if prompt_name in server_prompts:
                server_prompts.remove(prompt_name)
            log.info(f"Unregistered prompt '{prompt_name}' for server {server_id}")
            return True
        return False

    def get_prompt(self, server_id: str, prompt_name: str) -> PromptDefinition | None:
        return self._prompts.get(f"{server_id}:{prompt_name}")

    def get_server_prompts(self, server_id: str) -> list[PromptDefinition]:
        return [
            self._prompts[f"{server_id}:{name}"]
            for name in self._server_prompts.get(server_id, [])
            if f"{server_id}:{name}" in self._prompts
        ]

    def list_prompts(self) -> list[PromptDefinition]:
        return list(self._prompts.values())

    def find_by_category(self, category: str) -> list[PromptDefinition]:
        return [p for p in self._prompts.values() if category in p.categories]

    def find_by_tag(self, tag: str) -> list[PromptDefinition]:
        return [p for p in self._prompts.values() if tag in p.tags]

    def search_prompts(self, query: str) -> list[PromptDefinition]:
        q = query.lower()
        return [
            p for p in self._prompts.values() if q in p.name.lower() or q in p.description.lower()
        ]

    def enable_prompt(self, server_id: str, prompt_name: str) -> bool:
        prompt = self.get_prompt(server_id, prompt_name)
        if prompt:
            prompt.enabled = True
            prompt.updated_at = _utcnow()
            return True
        return False

    def disable_prompt(self, server_id: str, prompt_name: str) -> bool:
        prompt = self.get_prompt(server_id, prompt_name)
        if prompt:
            prompt.enabled = False
            prompt.updated_at = _utcnow()
            return True
        return False

    def get_enabled_prompts(self, server_id: str) -> list[PromptDefinition]:
        return [p for p in self.get_server_prompts(server_id) if p.enabled]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_prompts": len(self._prompts),
            "total_servers": len(self._server_prompts),
            "prompts_per_server": {sid: len(prs) for sid, prs in self._server_prompts.items()},
        }

    def clear_server(self, server_id: str) -> None:
        names = self._server_prompts.pop(server_id, [])
        for name in names:
            self._prompts.pop(f"{server_id}:{name}", None)

    def clear(self) -> None:
        self._prompts.clear()
        self._server_prompts.clear()


__all__ = [
    "MCPPromptRegistry",
    "PromptDefinition",
    "PromptArgument",
    "PROMPT_CATEGORIES",
]
