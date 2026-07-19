"""Learning engine event publisher — bridges learning events onto the EventBus.

Each method constructs the correct ``EventEnvelope`` and delegates to the
underlying ``EventBus.publish()``.  Follows the same pattern as
:class:`agentic_os.core.orchestration.publisher.OrchestrationEventPublisher`.
"""

from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("learning.publisher")


class LearningEventPublisher:
    """Publishes learning & optimization events to the EventBus.

    Each public method maps to a single :class:`Topic` value and constructs
    the :class:`EventEnvelope` with the appropriate payload.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    # ── Internal ──

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Low-level publish helper with error handling."""
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event",
                    source="learning-publisher",
                    topic=topic.value,
                    payload=payload,
                )
            )
        except Exception as exc:
            log.warning(
                "Failed to publish learning event",
                topic=topic.value,
                error=str(exc),
            )

    # ── Public Methods ──

    async def publish_execution_recorded(
        self,
        execution_id: str,
        target_id: str,
        target_type: str,
        outcome: str,
        duration_ms: float,
    ) -> None:
        await self._publish(
            Topic.LEARN_EXECUTION_RECORDED,
            {
                "execution_id": execution_id,
                "target_id": target_id,
                "target_type": target_type,
                "outcome": outcome,
                "duration_ms": duration_ms,
            },
        )

    async def publish_execution_profile_updated(
        self,
        target_id: str,
        target_type: str,
        success_rate: float,
        avg_duration_ms: float,
    ) -> None:
        await self._publish(
            Topic.LEARN_PROFILE_UPDATED,
            {
                "target_id": target_id,
                "target_type": target_type,
                "success_rate": success_rate,
                "avg_duration_ms": avg_duration_ms,
            },
        )

    async def publish_recommendation_generated(
        self,
        recommendation_id: str,
        target_id: str,
        recommendation_type: str,
        priority: str,
        title: str,
    ) -> None:
        await self._publish(
            Topic.LEARN_RECOMMENDATION_GENERATED,
            {
                "recommendation_id": recommendation_id,
                "target_id": target_id,
                "recommendation_type": recommendation_type,
                "priority": priority,
                "title": title,
            },
        )

    async def publish_recommendation_applied(
        self,
        recommendation_id: str,
        target_id: str,
    ) -> None:
        await self._publish(
            Topic.LEARN_RECOMMENDATION_APPLIED,
            {
                "recommendation_id": recommendation_id,
                "target_id": target_id,
            },
        )

    async def publish_benchmark_completed(
        self,
        benchmark_id: str,
        target_id: str,
        benchmark_name: str,
        score: float,
    ) -> None:
        await self._publish(
            Topic.LEARN_BENCHMARK_COMPLETED,
            {
                "benchmark_id": benchmark_id,
                "target_id": target_id,
                "benchmark_name": benchmark_name,
                "score": score,
            },
        )

    async def publish_prediction_made(
        self,
        prediction_id: str,
        target_id: str,
        prediction_type: str,
        predicted_value: float,
        confidence: float,
    ) -> None:
        await self._publish(
            Topic.LEARN_PREDICTION_MADE,
            {
                "prediction_id": prediction_id,
                "target_id": target_id,
                "prediction_type": prediction_type,
                "predicted_value": predicted_value,
                "confidence": confidence,
            },
        )

    async def publish_pattern_detected(
        self,
        pattern_id: str,
        pattern_type: str,
        target_type: str,
        severity: float,
    ) -> None:
        await self._publish(
            Topic.LEARN_PATTERN_DETECTED,
            {
                "pattern_id": pattern_id,
                "pattern_type": pattern_type,
                "target_type": target_type,
                "severity": severity,
            },
        )

    async def publish_knowledge_extracted(
        self,
        pattern_id: str,
        pattern_type: str,
        confidence: float,
    ) -> None:
        await self._publish(
            Topic.LEARN_KNOWLEDGE_EXTRACTED,
            {
                "pattern_id": pattern_id,
                "pattern_type": pattern_type,
                "confidence": confidence,
            },
        )

    async def publish_routing_decision(
        self,
        decision_id: str,
        task_id: str,
        selected_engine_id: str,
        confidence: float,
    ) -> None:
        await self._publish(
            Topic.LEARN_ROUTING_DECISION,
            {
                "decision_id": decision_id,
                "task_id": task_id,
                "selected_engine_id": selected_engine_id,
                "confidence": confidence,
            },
        )

    async def publish_optimization_applied(
        self,
        policy_id: str,
        target_id: str,
        metric: str,
        improvement: float,
    ) -> None:
        await self._publish(
            Topic.LEARN_OPTIMIZATION_APPLIED,
            {
                "policy_id": policy_id,
                "target_id": target_id,
                "metric": metric,
                "improvement": improvement,
            },
        )

    async def publish_anomaly_detected(
        self,
        target_id: str,
        metric: str,
        current_value: float,
        expected_value: float,
        deviation: float,
    ) -> None:
        await self._publish(
            Topic.LEARN_ANOMALY_DETECTED,
            {
                "target_id": target_id,
                "metric": metric,
                "current_value": current_value,
                "expected_value": expected_value,
                "deviation": deviation,
            },
        )

    async def publish_trend_changed(
        self,
        target_id: str,
        metric: str,
        direction: str,
        change_percent: float,
    ) -> None:
        await self._publish(
            Topic.LEARN_TREND_CHANGED,
            {
                "target_id": target_id,
                "metric": metric,
                "direction": direction,
                "change_percent": change_percent,
            },
        )

    async def publish_experience_recorded(
        self,
        experience_id: str,
        experience_type: str,
        source: str,
        reward: float,
    ) -> None:
        await self._publish(
            Topic.LEARN_EXPERIENCE_RECORDED,
            {
                "experience_id": experience_id,
                "experience_type": experience_type,
                "source": source,
                "reward": reward,
            },
        )
