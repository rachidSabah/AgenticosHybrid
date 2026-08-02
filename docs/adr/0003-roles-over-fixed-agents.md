# ADR-0003: Roles over fixed agent classes

- Status: Accepted
- Date: 2026-07-17

## Context

The product brief lists ~22 "primary agents" and ~26 "orchestration roles"
that heavily overlap (Coding/Backend/Frontend; Manager/Coordinator/Dispatcher).
Generating a distinct class per name would create ~48 near-duplicate modules,
hard to maintain and extend.

## Decision

Model a single generic `Agent` runtime instantiated with a declarative `Role`
(prompt template + allowed tools + default provider). Roles are registered in
the `AgentRegistry`. Adding capability is adding a Role, not a class.

## Consequences

- Drastically less duplication; one runtime path to test.
- New behaviors are data (roles), not code.
- The 22/26 named capabilities map to role configs, preserving the brief's
  vocabulary without the architectural cost.
