"""Cognitive Memory — extends ExecutiveMemory with cognitive indexes.

Does NOT replace ExecutiveMemory or MemoryManager. Only adds cognitive
indexes: objectives, predictions, experience records, evaluation scores,
improvement proposals, world model snapshots, and knowledge graph nodes.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger("cognitive.memory")


class CognitiveMemory:
    """Cognitive-specific indexes over the existing memory system."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._objectives: dict[str, dict[str, Any]] = {}
        self._predictions: dict[str, dict[str, Any]] = {}
        self._experience: dict[str, dict[str, Any]] = {}
        self._evaluations: dict[str, dict[str, Any]] = {}
        self._improvements: dict[str, dict[str, Any]] = {}
        self._failures: dict[str, dict[str, Any]] = {}
        self._reflections: dict[str, dict[str, Any]] = {}  # mirror of exec reflections
        self._world_snapshots: list[dict[str, Any]] = []
        self._kg_nodes: dict[str, dict[str, Any]] = {}
        self._kg_edges: list[dict[str, Any]] = []

    # ── Objectives ───────────────────────────────────────────────────

    async def store_reflection(self, ref_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._reflections[ref_id] = data

    async def list_reflections(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._reflections.values())[-limit:]

    async def store_objective(self, obj_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._objectives[obj_id] = data

    async def get_objective(self, obj_id: str) -> dict[str, Any] | None:
        async with self._lock:
            return self._objectives.get(obj_id)

    async def list_objectives(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._objectives.values())[-limit:]

    # ── Predictions ──────────────────────────────────────────────────

    async def store_prediction(self, pred_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._predictions[pred_id] = data

    async def list_predictions(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._predictions.values())[-limit:]

    # ── Experience records ───────────────────────────────────────────

    async def store_experience(self, exp_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._experience[exp_id] = data

    async def list_experience(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._experience.values())[-limit:]

    # ── Failures ────────────────────────────────────────────────────

    async def store_failure(self, failure_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._failures[failure_id] = data

    async def list_failures(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._failures.values())[-limit:]

    # ── Evaluations ──────────────────────────────────────────────────

    async def store_evaluation(self, eval_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._evaluations[eval_id] = data

    async def list_evaluations(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._evaluations.values())[-limit:]

    # ── Improvements ─────────────────────────────────────────────────

    async def store_improvement(self, imp_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._improvements[imp_id] = data

    async def list_improvements(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._improvements.values())[-limit:]

    # ── World Model snapshots ────────────────────────────────────────

    async def store_world_snapshot(self, snapshot: dict[str, Any]) -> None:
        async with self._lock:
            self._world_snapshots.append(snapshot)
            if len(self._world_snapshots) > 100:
                self._world_snapshots = self._world_snapshots[-100:]

    async def get_latest_world_snapshot(self) -> dict[str, Any] | None:
        async with self._lock:
            return self._world_snapshots[-1] if self._world_snapshots else None

    # ── Knowledge Graph ──────────────────────────────────────────────

    async def add_kg_node(self, node_id: str, node_type: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._kg_nodes[node_id] = {"id": node_id, "type": node_type, "data": data}

    async def add_kg_edge(
        self, source: str, target: str, rel_type: str, data: dict[str, Any] | None = None
    ) -> None:
        async with self._lock:
            self._kg_edges.append(
                {"source": source, "target": target, "type": rel_type, "data": data or {}}
            )

    async def get_kg(self) -> dict[str, Any]:
        async with self._lock:
            return {"nodes": list(self._kg_nodes.values()), "edges": list(self._kg_edges)}

    async def kg_neighbors(self, node_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                {**e, "neighbor": e["target"] if e["source"] == node_id else e["source"]}
                for e in self._kg_edges
                if e["source"] == node_id or e["target"] == node_id
            ]

    # ── Metrics ───────────────────────────────────────────────────────

    async def metrics(self) -> dict[str, int]:
        async with self._lock:
            return {
                "objectives_indexed": len(self._objectives),
                "predictions_indexed": len(self._predictions),
                "experience_indexed": len(self._experience),
                "evaluations_indexed": len(self._evaluations),
                "improvements_indexed": len(self._improvements),
                "world_snapshots": len(self._world_snapshots),
                "kg_nodes": len(self._kg_nodes),
                "kg_edges": len(self._kg_edges),
            }
