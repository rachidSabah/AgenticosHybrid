"""Objective Manager — manages long-term objectives lifecycle.

Supports: create, update, cancel, archive, prioritize, merge, split.
Objectives link to Goals and Missions via IDs.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agentic_os.core.cognitive.domain import LongTermObjective, ObjectivePriority, ObjectiveStatus
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.ports.event_bus import EventBus

log = get_logger("cognitive.objectives")


class ObjectiveManager:
    """Manages the lifecycle of long-term objectives."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus
        self._objectives: dict[str, LongTermObjective] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        title: str,
        description: str = "",
        priority: ObjectivePriority = ObjectivePriority.NORMAL,
        owner: str = "",
        success_metrics: list[str] | None = None,
        dependencies: list[str] | None = None,
        deadline: str = "",
        estimated_value: float = 0.0,
        estimated_cost: float = 0.0,
        risk: float = 0.0,
    ) -> LongTermObjective:
        obj = LongTermObjective(
            title=title,
            description=description,
            priority=priority,
            owner=owner,
            success_metrics=success_metrics,
            dependencies=dependencies,
            deadline=deadline,
            estimated_value=estimated_value,
            estimated_cost=estimated_cost,
            risk=risk,
        )
        async with self._lock:
            self._objectives[obj.id] = obj
        await self._publish("cognitive.objective.created", obj.to_dict())
        log.info("Created objective %s (%s)", obj.id, obj.title)
        return obj

    async def update(self, obj_id: str, **fields: object) -> LongTermObjective | None:
        async with self._lock:
            obj = self._objectives.get(obj_id)
            if obj is None:
                return None
            for k, v in fields.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
            obj.updated_at = datetime.now(UTC).isoformat()
        await self._publish("cognitive.objective.updated", obj.to_dict())
        return obj

    async def cancel(self, obj_id: str) -> LongTermObjective | None:
        async with self._lock:
            obj = self._objectives.get(obj_id)
            if obj is None:
                return None
            obj.status = ObjectiveStatus.CANCELLED
            obj.updated_at = datetime.now(UTC).isoformat()
        await self._publish("cognitive.objective.cancelled", obj.to_dict())
        return obj

    async def archive(self, obj_id: str) -> LongTermObjective | None:
        async with self._lock:
            obj = self._objectives.get(obj_id)
            if obj is None:
                return None
            if obj.status not in (
                ObjectiveStatus.COMPLETED,
                ObjectiveStatus.FAILED,
                ObjectiveStatus.CANCELLED,
            ):
                return None
            obj.status = ObjectiveStatus.ARCHIVED
            obj.updated_at = datetime.now(UTC).isoformat()
        await self._publish("cognitive.objective.archived", obj.to_dict())
        return obj

    async def activate(self, obj_id: str) -> LongTermObjective | None:
        async with self._lock:
            obj = self._objectives.get(obj_id)
            if obj is None:
                return None
            obj.status = ObjectiveStatus.ACTIVE
            obj.updated_at = datetime.now(UTC).isoformat()
        await self._publish("cognitive.objective.activated", obj.to_dict())
        return obj

    async def prioritize(
        self, obj_id: str, priority: ObjectivePriority
    ) -> LongTermObjective | None:
        async with self._lock:
            obj = self._objectives.get(obj_id)
            if obj is None:
                return None
            obj.priority = priority
            obj.updated_at = datetime.now(UTC).isoformat()
        await self._publish("cognitive.objective.prioritized", obj.to_dict())
        return obj

    async def merge(self, obj_ids: list[str], new_title: str) -> LongTermObjective | None:
        async with self._lock:
            objs: list[LongTermObjective] = [
                o for oid in obj_ids if (o := self._objectives.get(oid)) is not None
            ]
            if len(objs) < 2:
                return None
            for o in objs:
                o.status = ObjectiveStatus.ARCHIVED
                o.updated_at = datetime.now(UTC).isoformat()
            merged = LongTermObjective(
                title=new_title,
                description=" | ".join(o.title for o in objs),
                priority=max(o.priority for o in objs),
                dependencies=list({d for o in objs for d in o.dependencies}),
            )
            self._objectives[merged.id] = merged
        await self._publish("cognitive.objective.merged", merged.to_dict())
        return merged

    async def split(self, obj_id: str, sub_titles: list[str]) -> list[LongTermObjective]:
        async with self._lock:
            parent = self._objectives.get(obj_id)
            if parent is None or len(sub_titles) < 2:
                return []
            parent.status = ObjectiveStatus.ARCHIVED
            parent.updated_at = datetime.now(UTC).isoformat()
            children: list[LongTermObjective] = []
            for title in sub_titles:
                child = LongTermObjective(
                    title=title,
                    description=f"Sub-objective of {parent.title}",
                    priority=parent.priority,
                    dependencies=[obj_id],
                )
                self._objectives[child.id] = child
                children.append(child)
        for child in children:
            await self._publish("cognitive.objective.created", child.to_dict())
        return children

    async def get(self, obj_id: str) -> LongTermObjective | None:
        async with self._lock:
            return self._objectives.get(obj_id)

    async def list_all(self) -> list[LongTermObjective]:
        async with self._lock:
            return list(self._objectives.values())

    async def _publish(self, topic: str, payload: dict) -> None:
        if self._bus is None:
            return
        from agentic_os.domain.events import EventEnvelope

        try:
            await self._bus.publish(
                EventEnvelope(
                    type=topic, source="cognitive.objectives", topic=topic, payload=payload
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)
