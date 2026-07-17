# ADR-0006: Provider Management System

- Status: Accepted
- Date: 2026-07-17
- Phase: 2 (Subsystem 1)

## Context

The Phase-1 `ProviderRegistry` only tracked adapters for the orchestrator. We
need full provider lifecycle management: models + economics, secret storage,
health, benchmarking, failover, routing policies, cost tracking, and rate
limits — plus the ability to add OpenAI-compatible custom providers at runtime
from a UI/API. This must not disturb the frozen `ProviderAdapter`/`EventBus`
ports.

## Decision

Introduce `ports/provider_management.py` declaring: `ProviderManager`,
`ModelManager`, `SecretStore`, `ApiKeyVault`, `ProviderHealthMonitor`,
`RoutingPolicy`, `CostTracker`, `RateLimitMonitor`, `FailoverPolicy`, plus the
`ModelInfo` entity. Concrete implementations live in `core/providers/` and
`adapters/security/` (encrypted secret store via Fernet). A `ProviderRouter`
facade composes manager + health + policy + rate-limit + failover into one
decision point.

The `ProviderManager` becomes the authoritative catalog; the kernel seeds it
from the Phase-1 plugin-loaded adapters so both the old `ProviderRegistry`
(orchestrator dispatch) and the new manager coexist. OpenAI-compatible providers
are instantiated from `ProviderConfig` via `adapters/providers/factory.py`,
pulling secrets from the `ApiKeyVault` (never from the config payload).

## Consequences

- Providers/models are now first-class, queryable, and observable.
- Secrets are encrypted at rest; plaintext keys are never logged or returned.
- Routing policies (latency/cost/round-robin) and automatic failover are real
  and tested.
- Adding a custom OpenAI-compatible endpoint is a single REST call + key store.
- The orchestrator's dispatch path is intentionally left on `ProviderRegistry`
  for Phase 1 compatibility; capability-aware dispatch (S3) will consult the
  router, completing the integration.

## New event topics

`provider.health`, `provider.registered`, `provider.failed`, `provider.failover`,
`cost.recorded` (see `domain/events.py`).
