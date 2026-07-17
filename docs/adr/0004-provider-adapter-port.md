# ADR-0004: Provider adapters behind a port

- Status: Accepted
- Date: 2026-07-17

## Context

The OS must integrate 18+ provider backends (Claude Code, OpenAI, Gemini, Ollama,
…). Each has a different SDK/auth/streaming model. Tightly coupling orchestration
to any one breaks the "replaceable" requirement.

## Decision

A `ProviderAdapter` port (`ports/provider.py`) defines `execute(agent, task)`
and `healthcheck()`. Concrete adapters (Mock, Claude Code, and future OpenAI/
Gemini/…) implement it and register in `ProviderRegistry` via plugins. The
orchestrator depends only on the port.

## Consequences

- Adding a provider is adding an adapter + plugin, no core change.
- Adapters are side-effect-isolated (shell out / call SDK, raise on failure).
- The Supervisor/Recovery layer reacts uniformly to adapter failures.
