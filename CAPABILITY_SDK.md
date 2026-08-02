# Capability SDK (spec — deferred to Phase 3)

Status: **Planned (Phase 3).** The capability engine is implemented and frozen
(see `ports/capability.py` and `docs/adr/0007-capability-engine.md`). This
document will formalize how third parties add capabilities.

## What will be specified

- `Capability` protocol (`name`, `description`, `requires_approval`,
  `run(agent, task, context) -> CapabilityResult`).
- `CapabilityResult` shape (`ok`, `output`, `meta`).
- Built-in capability base classes (`_Base`, `_ShellCapability`) in
  `adapters/capability/builtins.py`.
- Registering a capability with `CapabilityRegistry`.
- How `requires_approval=True` flows into the Security Framework approval gate.

Until published, add capabilities by subclassing the built-in bases and
registering them with the engine's registry.
