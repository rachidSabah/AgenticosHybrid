"""Communication Bus — inter-agent messaging over EventBus.

Provides point-to-point, broadcast, and request-response messaging patterns
for agents within a swarm. Messages are stored in a ring buffer for history.
"""

from collections import deque
from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import AgentMessage
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("orchestration.communication")


class CommunicationBus:
    """Handles inter-agent messaging over EventBus.

    Maintains an in-memory ring buffer of sent messages for history retrieval.
    Supports direct messaging, broadcast within a swarm, and request-response
    correlation.
    """

    def __init__(self, bus: EventBus, history_max: int = 1000) -> None:
        self._bus = bus
        self._history_max = history_max
        self._history: deque[AgentMessage] = deque(maxlen=history_max)

    async def send_message(self, message: AgentMessage) -> AgentMessage:
        """Send a direct message from one agent to another (or broadcast).

        Publishes an ``ORCH_MSG_SENT`` event and records in history.
        """
        await self._publish(
            Topic.ORCH_MSG_SENT,
            {
                "message_id": message.id,
                "source_agent_id": message.source_agent_id,
                "target_agent_id": message.target_agent_id,
                "swarm_id": message.swarm_id,
                "message_type": message.message_type,
            },
        )

        # Record in history
        self._history.append(message)

        log.debug(
            "Message sent",
            msg_id=message.id,
            source=message.source_agent_id,
            target=message.target_agent_id or "(broadcast)",
        )

        return message

    async def broadcast(
        self,
        source_agent_id: str,
        swarm_id: str,
        payload: dict[str, Any],
        message_type: str = "broadcast",
    ) -> AgentMessage:
        """Broadcast a message to all agents in a swarm."""
        message = AgentMessage(
            source_agent_id=source_agent_id,
            target_agent_id=None,  # None = broadcast
            swarm_id=swarm_id,
            message_type=message_type,
            payload=payload,
        )

        await self._publish(
            Topic.ORCH_MSG_BROADCAST,
            {
                "message_id": message.id,
                "source_agent_id": source_agent_id,
                "swarm_id": swarm_id,
                "message_type": message_type,
            },
        )

        self._history.append(message)

        log.info(
            "Broadcast sent",
            msg_id=message.id,
            source=source_agent_id,
            swarm_id=swarm_id,
        )

        return message

    async def send_response(
        self,
        original: AgentMessage,
        response_payload: dict[str, Any],
    ) -> AgentMessage:
        """Send a response correlated to an original message."""
        response = original.with_response(response_payload)
        return await self.send_message(response)

    async def receive_message(
        self,
        message: AgentMessage,
    ) -> AgentMessage:
        """Handle an incoming message — records receipt event.

        Returns the message unchanged. The subscriber is responsible
        for any processing.
        """
        await self._publish(
            Topic.ORCH_MSG_RECEIVED,
            {
                "message_id": message.id,
                "source_agent_id": message.source_agent_id,
                "target_agent_id": message.target_agent_id,
                "swarm_id": message.swarm_id,
            },
        )

        log.debug(
            "Message received",
            msg_id=message.id,
            source=message.source_agent_id,
            target=message.target_agent_id or "(broadcast)",
        )

        return message

    async def get_history(
        self,
        limit: int = 50,
        swarm_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[AgentMessage]:
        """Get recent message history, optionally filtered.

        Args:
            limit: Maximum messages to return.
            swarm_id: Optional filter by swarm.
            agent_id: Optional filter by agent (source or target).
        """
        result: list[AgentMessage] = list(self._history)

        if swarm_id:
            result = [m for m in result if m.swarm_id == swarm_id]
        if agent_id:
            result = [
                m for m in result if m.source_agent_id == agent_id or m.target_agent_id == agent_id
            ]

        # Reverse to show most recent first
        result.reverse()
        return result[:limit]

    async def clear_history(self) -> None:
        """Clear all message history."""
        self._history.clear()

    @property
    def history_size(self) -> int:
        """Current number of messages in history."""
        return len(self._history)

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Publish a communication event to the EventBus."""
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event",
                    source="communication-bus",
                    topic=topic.value,
                    payload=payload,
                )
            )
        except Exception as exc:
            log.warning(
                "Failed to publish communication event",
                topic=topic.value,
                error=str(exc),
            )
