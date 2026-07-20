"""Learning event publisher — publishes learning events via EventBus."""

from typing import Any

from agentic_os.domain.events import EventEnvelope
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("learning.publisher")


class LearningEventPublisher:
    """Publishes learning events via the EventBus."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event", source="learning-publisher", topic=topic, payload=payload
                )
            )
        except Exception as exc:
            log.warning("Failed to publish learning event", topic=topic, error=str(exc))

    async def publish_learning_started(self, profile_id: str) -> None:
        await self._publish("learning.started", {"profile_id": profile_id})

    async def publish_learning_completed(self, profile_id: str) -> None:
        await self._publish("learning.completed", {"profile_id": profile_id})

    async def publish_optimization(self, optimization_id: str, target: str, status: str) -> None:
        await self._publish(
            "optimization.applied",
            {"optimization_id": optimization_id, "target": target, "status": status},
        )

    async def publish_recommendation(
        self, recommendation_id: str, category: str, confidence: float
    ) -> None:
        await self._publish(
            "recommendation.generated",
            {
                "recommendation_id": recommendation_id,
                "category": category,
                "confidence": confidence,
            },
        )

    async def publish_benchmark(self, benchmark_id: str, status: str) -> None:
        await self._publish("benchmark.completed", {"benchmark_id": benchmark_id, "status": status})

    async def publish_evaluation(self, evaluation_id: str, target_type: str, score: float) -> None:
        await self._publish(
            "evaluation.completed",
            {"evaluation_id": evaluation_id, "target_type": target_type, "score": score},
        )

    async def publish_experiment(self, experiment_id: str, status: str) -> None:
        await self._publish(
            "experiment.status_changed", {"experiment_id": experiment_id, "status": status}
        )

    async def publish_policy(self, policy_id: str, action: str) -> None:
        await self._publish("policy.updated", {"policy_id": policy_id, "action": action})


__all__ = ["LearningEventPublisher"]
