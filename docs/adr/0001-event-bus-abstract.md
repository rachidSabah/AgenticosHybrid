# ADR-0001: Abstract Event Bus as the system spine

- Status: Accepted
- Date: 2026-07-17

## Context

The Agentic OS must orchestrate unlimited agents across providers with every
component modular and replaceable. A monolithic call graph would couple agents,
supervision, and UI. We need a uniform coordination mechanism.

## Decision

All coordination flows through a single abstract `EventBus` protocol
(`ports/event_bus.py`). Three interchangeable adapters implement it:

- `LocalBus` — in-process asyncio (dev/tests/zero-infra)
- `RedisStreamsBus` — default production (persistent, replayable, consumer groups)
- `NatsJetStreamBus` — supported alternative (strong routing + KV + replay)

Selection is config-driven (`BUS_TYPE`) via `adapters/bus/factory.py`. No
caller imports a concrete bus.

## Consequences

- Swapping transports is a config change, not a code change.
- Producers/consumers are decoupled and independently testable.
- Redis/NATS add operational dependencies only in production.
- LocalBus is the reference implementation and the CI default.
