# Plugin SDK (spec — deferred to Phase 3)

Status: **Planned (Phase 3).** A plugin loader already exists
(`adapters/plugins/loader.py`) and the `Plugin` port (`name`, `load()`,
`unload()`) is frozen. This document will formalize the marketplace-ready
extension contract.

## What will be specified

- The `Plugin` interface and discovery conventions.
- How `load()` registers providers/agents into the registries.
- Packaging, signing, and versioning for the Phase 4 Plugin Marketplace.
- Isolation and permission boundaries for third-party plugins.

Until published, drop plugin modules discoverable by the loader; they receive a
`PluginContext` with the agent/provider registries.
