# Provider SDK (spec — deferred to Phase 3)

Status: **Planned (Phase 3).** The provider *abstraction* is already frozen and
implemented (see `ports/provider.py` → `ProviderAdapter`, and the Provider
Management subsystem in `docs/adr/0006-provider-management.md`). This document
will formalize the third-party extension contract.

## What will be specified

- `ProviderAdapter` interface (`info`, `execute()`, `healthcheck()`).
- `ProviderConfig` fields and validation rules.
- How to register a provider via `POST /api/provider-configs` and the
  `build_adapter` factory (`adapters/providers/factory.py`).
- Secret handling via the encrypted vault (`ApiKeyVault` / `SecretStore`).
- Health, routing, cost, and rate-limit integration points.

Until published, implement providers directly against `ProviderAdapter` in
`src/agentic_os/adapters/providers/`.
