from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActorType(StrEnum):
    SYSTEM = "system"
    AGENT = "agent"
    USER = "user"
    PLUGIN = "plugin"
    WORKFLOW = "workflow"


class ActorRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(description="Actor kind (system, agent, user, plugin, workflow).")
    id: str = Field(description="Unique identifier within the kind.")
    label: str | None = Field(default=None, description="Human-readable label.")
