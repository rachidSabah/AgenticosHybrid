# ADR-0007: Capability Engine

- Status: Accepted
- Date: 2026-07-17
- Phase: 2 (Subsystem 3)

## Context

Phase 1 modelled agents using fixed `Role` values (`coding`, `research`, …).
That is rigid: adding a new competence means editing the `Role` enum and the
orchestrator dispatch, and there is no way to assemble an agent that is, say,
*a researcher that can also run the terminal* without bolting on a new role.

We want agents to be composed from small, independently implementable and
testable units of competence — *capabilities* — at runtime. This mirrors how
the Provider Management subsystem treats providers as swappable adapters: the
same hexagonal discipline, applied to agent competence.

## Decision

1. **Capabilities are the unit of agent definition.** A `Capability` (port,
   `ports/capability.py`) is a `Protocol` with `name`, `description`,
   `requires_approval`, and an async `run(agent, task, context) -> CapabilityResult`.
   Sensitive capabilities (`terminal`, `git`, `docker`, `filesystem`) set
   `requires_approval = True` so the Security Framework's approval gate
   (ADR-0009, Subsystem 4) can intercept them before `run` executes.

2. **An `AgentSpec` replaces the fixed `Role`.** `domain/capability.py` defines
   `AgentSpec` (name, ordered `capabilities`, provider, model, system_prompt,
   `requires_approval`). The orchestrator's static `Role` enum is preserved for
   backwards-compatible dispatch but is no longer the *definition* of an agent.

3. **Registry + Composer core.** `core/capability/engine.py` provides:
   - `CapabilityRegistryImpl` — catalog of capabilities with
     `requires_approval(names)` aggregation.
   - `AgentComposerImpl` — `compose(name, capabilities, provider, model)` builds
     an `AgentSpec` and propagates the approval flag; `spec_for_task(task)`
     derives a capability set from a lightweight intent→capability map
     (`code`, `research`, `plan`, `review`, `infra`).
   - `CapabilityEngine` — top-level subsystem; `start()` seeds the 11 built-ins
     and `compose_and_emit(task)` publishes an `AGENT_COMPOSED` event.

4. **Built-ins shipped.** `adapters/capability/builtins.py` implements 11
   capabilities. Cognitive/knowledge ones return static `CapabilityResult`s
   (the provider does the real work); shell-backed ones (`_ShellCapability`)
   execute via `asyncio.create_subprocess_exec` scoped to the agent workspace.

5. **REST surface.** `api/app.py` exposes `/api/capabilities`,
   `/api/agents/compose`, and `/api/agents/compose-for-task`.

## Consequences

- Agents are now data-driven compositions, not enum members. New competence = a
  new `Capability` class + registration, with zero orchestrator changes.
- Approval intent is declared at the capability level, giving the Security
  Framework a clean, declarative gate (see ADR-0009).
- Public interface frozen: `Capability`, `CapabilityResult`, `CapabilityRegistry`,
  `AgentComposer` ports; `AgentSpec` domain entity; `CapabilityEngine.start`,
  `compose_and_emit`.
- The LocalBus `stop()` now drains in-flight dispatches (gather pending tasks)
  so subscribers observe events published immediately before shutdown — this is
  a behavioural fix required for event-driven tests and the dashboard.

## Alternatives considered

- *Keep fixed roles, add a `capabilities` field to `Role`.* Rejected: still
  requires editing the enum and does not give independent testability/approval
  semantics per competence.
- *Composition done in the orchestrator.* Rejected: violates hexagonal
  separation (orchestrator should depend on the capability port, not own the
  composition logic).
