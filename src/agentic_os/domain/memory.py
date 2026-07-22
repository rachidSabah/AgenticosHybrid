"""Domain entities for the Memory System.

Memory is partitioned into named *scopes* (working memory, conversation, project,
shared, long-term). Each stored item is a :class:`MemoryItem` with a scope, an
optional TTL, and an embedding vector for similarity search (when a vector store
is configured). Retention policies (TTL / max-size) live at the scope level —
see :mod:`agentic_os.core.memory.lifecycle`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MemoryScope(StrEnum):
    """Logical partitions of memory."""

    WORKING = "working"  # short-lived scratch space for the current task
    CONVERSATION = "conversation"  # per-session dialogue turns
    PROJECT = "project"  # durable context scoped to a project/workspace
    SHARED = "shared"  # cross-agent shared knowledge
    LONG_TERM = "long_term"  # persisted, indexed facts/embeddings


class MemoryItem(BaseModel):
    """A single stored memory record."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    scope: MemoryScope
    key: str
    value: str
    embedding: list[float] = Field(default_factory=list)
    agent_id: str = ""
    project_id: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime | None = None  # None = never expires

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return _utcnow() >= self.expires_at
