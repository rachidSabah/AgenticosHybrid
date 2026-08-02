# ADR-0002: Hexagonal (Clean) Architecture

- Status: Accepted
- Date: 2026-07-17

## Context

The brief demands modularity and replaceability. A layered architecture with a
fat core would make swapping the bus, provider, or UI painful.

## Decision

Ports (interfaces) live in `ports/`. Domain entities in `domain/`. Core logic
in `core/` depends only on ports. Concrete implementations (bus adapters,
providers, plugins, FastAPI) live in `adapters/` and `api/` and depend inward.
The composition root is `kernel.py` — the only place that knows concrete types.

## Consequences

- Core logic is unit-testable with fake ports (e.g. LocalBus).
- New providers/plugins/UIs are added without touching core.
- A single composition root makes the dependency graph auditable.
