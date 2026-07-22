"""Domain entities for the Capability Engine.

An :class:`AgentSpec` is a dynamic agent definition: a name, the ordered set of
capabilities it composes, and the provider/model it executes on. This replaces
the static Phase-1 ``Role`` as the unit of agent definition (ADR-0007).
"""

from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class CapabilityCategory(StrEnum):
    COGNITION = "cognition"  # reasoning, planning
    CODE = "code"  # coding, git, filesystem, terminal, docker
    KNOWLEDGE = "knowledge"  # research, memory, vision, browser
    EXECUTION = "execution"  # runtime execution environments


class AgentSpec(BaseModel):
    """A dynamically composed agent specification."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    capabilities: list[str] = Field(default_factory=list)
    provider: str = ""
    model: str = ""
    system_prompt: str = ""
    requires_approval: bool = False

    def with_provider(self, provider: str, model: str) -> AgentSpec:
        return self.model_copy(update={"provider": provider, "model": model})
