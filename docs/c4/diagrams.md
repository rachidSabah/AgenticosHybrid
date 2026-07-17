# C4 Architecture Diagrams

## Context (C4 Level 1)

```mermaid
C4Context
    title Agentic OS — System Context
    Person(user, "Operator / Developer", "Issues requests, approves actions")
    System(aos, "Agentic OS", "Local-first agent operating system")
    System_Ext(providers, "Provider Backends", "Claude Code, OpenAI, Gemini, Ollama, ...")
    System_Ext(businfra, "Bus Infrastructure", "Redis / NATS (prod only)")

    Rel(user, aos, "Submits tasks, views live dashboard")
    Rel(aos, providers, "Executes tasks via adapters")
    Rel(aos, businfra, "Pub/sub events (prod)")
```

## Container (C4 Level 2)

```mermaid
C4Container
    title Agentic OS — Containers
    Person(user, "Operator")

    Container(api, "FastAPI Control Plane", "Python/FastAPI", "REST + WebSocket dashboard")
    Container(core, "Orchestrator Kernel", "Python", "Planner, Dispatcher, Supervisor, Recovery, Health")
    Container(bus, "Event Bus", "Local/Redis/NATS", "Abstract pub/sub spine")
    Container(plugins, "Plugin Loader + Providers", "Python", "Mock, Claude Code, future adapters")
    Container(ui, "Dashboard (WebSocket)", "Browser", "Live event stream")

    Rel(user, api, "HTTP / WS")
    Rel(api, core, "Commands")
    Rel(core, bus, "Publish/Subscribe")
    Rel(core, plugins, "Execute tasks")
    Rel(bus, ui, "Live events")
```

## Component (C4 Level 3 — Orchestrator)

```mermaid
C4Component
    title Orchestrator Kernel — Components
    Container_Boundary(core, "Core") {
        Component(planner, "Planner", "task.created -> task.planned")
        Component(dispatcher, "Task Dispatcher", "plans -> spawns agent -> runs provider")
        Component(supervisor, "Supervisor", "observes completion/failure")
        Component(health, "Health Monitor", "periodic liveness checks")
        Component(recovery, "Recovery Manager", "retry on failure (capped)")
    }
    Container(bus, "Event Bus")
    Container(reg, "AgentRegistry / ProviderRegistry")

    Rel(planner, bus, "publish planned")
    Rel(dispatcher, bus, "subscribe planned, publish dispatched")
    Rel(supervisor, bus, "publish completed/failed")
    Rel(health, bus, "publish health")
    Rel(recovery, bus, "subscribe failed, redispatch")
    Rel(dispatcher, reg, "spawn agent, lookup provider")
```
