"""Bus factory — selects the adapter from configuration.

``BUS_TYPE`` chooses the implementation; the rest of the system only ever sees
the :class:`EventBus` protocol. Swapping transports requires no call-site change.
"""

from __future__ import annotations

from agentic_os.config import Settings
from agentic_os.ports.event_bus import EventBus


def build_bus(settings: Settings) -> EventBus:
    if settings.bus_type == "redis":
        from agentic_os.adapters.bus.redis_streams import create_redis_bus

        return create_redis_bus(settings.redis_url)
    if settings.bus_type == "nats":
        from agentic_os.adapters.bus.nats_jetstream import create_nats_bus

        return create_nats_bus(settings.nats_url)
    from agentic_os.adapters.bus.local import create_local_bus

    return create_local_bus()
