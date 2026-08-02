import { describe, it, expect, beforeEach } from "vitest";
import { useStore } from "./store";
import type { EventEnvelope } from "./types";

function envelope(topic: string, payload: Record<string, unknown> = {}): EventEnvelope {
  return {
    id: Math.random().toString(36).slice(2),
    type: "event",
    source: "test",
    topic,
    timestamp: new Date().toISOString(),
    payload,
  };
}

describe("event store", () => {
  beforeEach(() => {
    useStore.setState({
      events: [],
      agents: {},
      tasks: {},
      providers: {},
      memory: [],
      audit: [],
      notifications: [],
      missions: {},
      missionUpdates: 0,
      telemetry: {
        tasks: 0,
        agents: 0,
        providers: 0,
        pipelines: 0,
        tokens: 0,
        cost: 0,
        latency: 0,
        errors: 0,
        pulses: [],
      },
    });
  });

  it("ingests agent.started into the agents map", () => {
    useStore.getState().ingest(envelope("agent.started", { id: "a1", role: "planner", provider: "mock" }));
    const a = useStore.getState().agents["a1"];
    expect(a).toBeDefined();
    expect(a.status).toBe("running");
    expect(a.provider).toBe("mock");
    expect(useStore.getState().telemetry.agents).toBe(1);
  });

  it("ingests provider health and counts errors on failure", () => {
    useStore.getState().ingest(envelope("provider.health", { provider: "p1", status: "healthy", latency_ms: 12 }));
    useStore.getState().ingest(envelope("provider.failed", { provider: "p2", status: "down", error: "x" }));
    expect(useStore.getState().providers["p1"].status).toBe("healthy");
    expect(useStore.getState().providers["p2"].status).toBe("down");
    expect(useStore.getState().telemetry.errors).toBe(1);
    expect(useStore.getState().telemetry.providers).toBe(2);
  });

  it("accumulates cost from cost.recorded", () => {
    useStore.getState().ingest(envelope("cost.recorded", { amount: 0.5 }));
    useStore.getState().ingest(envelope("cost.recorded", { amount: 0.25 }));
    expect(useStore.getState().telemetry.cost).toBeCloseTo(0.75);
  });

  it("keeps a rolling pulse ring from agent.composed", () => {
    useStore.getState().ingest(envelope("agent.composed", {}));
    expect(useStore.getState().telemetry.pipelines).toBe(1);
    expect(useStore.getState().telemetry.pulses.length).toBeGreaterThan(0);
  });

  it("emits a notification for each ingested event", () => {
    useStore.getState().ingest(envelope("task.created", { id: "t1", title: "x" }));
    const n = useStore.getState().notifications[0];
    expect(n.topic).toBe("task.created");
    expect(n.level).toBe("info");
  });

  it("ingests brain.registered into agents + providers", () => {
    useStore.getState().ingest(
      envelope("brain.registered", {
        id: "b1",
        display_name: "Claude Code",
        health: 80,
        latency: 12,
        capabilities: ["coding"],
      })
    );
    expect(useStore.getState().agents["b1"]).toBeDefined();
    expect(useStore.getState().agents["b1"].provider).toBe("Claude Code");
    expect(useStore.getState().providers["Claude Code"]).toBeDefined();
    expect(useStore.getState().providers["Claude Code"].status).toBe("healthy");
    expect(useStore.getState().telemetry.agents).toBe(1);
    expect(useStore.getState().telemetry.providers).toBe(1);
  });

  it("removes agent + provider on brain.removed", () => {
    // Seed: register a brain
    useStore.getState().ingest(
      envelope("brain.registered", {
        id: "b2",
        display_name: "Hermes",
        health: 80,
        latency: 12,
      })
    );
    expect(useStore.getState().agents["b2"]).toBeDefined();
    expect(useStore.getState().providers["Hermes"]).toBeDefined();

    // Remove
    useStore.getState().ingest(
      envelope("brain.removed", {
        id: "b2",
        display_name: "Hermes",
      })
    );
    expect(useStore.getState().agents["b2"]).toBeUndefined();
    expect(useStore.getState().providers["Hermes"]).toBeUndefined();
  });

  it("updates health on brain.health_changed", () => {
    useStore.getState().ingest(
      envelope("brain.registered", {
        id: "b3",
        display_name: "Ollama",
        health: 80,
        latency: 12,
      })
    );
    useStore.getState().ingest(
      envelope("brain.health_changed", {
        id: "b3",
        display_name: "Ollama",
        health: 30,
        latency: 50,
      })
    );
    // health < 50 → status "unknown"
    expect(useStore.getState().providers["Ollama"].status).toBe("unknown");
  });

  it("inserts a NEW mission on mission.created (Prompt Center → Mission Orchestrator connection)", () => {
    // Simulate what happens when Prompt Center submits a mission:
    // the backend publishes mission.created with the full mission payload.
    useStore.getState().ingest(
      envelope("mission.created", {
        id: "m-new-1",
        title: "Build FastAPI auth",
        description: "Build a production FastAPI authentication service.",
        prompt: "Build a production FastAPI authentication service.",
        status: "created",
        priority: "high",
        execution_mode: "hybrid",
        created_at: new Date().toISOString(),
      })
    );
    const missions = useStore.getState().missions;
    // The new mission must be in the store — previously this was dropped
    // because the handler only updated EXISTING missions.
    expect(missions["m-new-1"]).toBeDefined();
    expect(missions["m-new-1"].title).toBe("Build FastAPI auth");
    expect(missions["m-new-1"].status).toBe("created");
    // missionUpdates must bump so subscribers (Mission Orchestrator) re-render
    expect(useStore.getState().missionUpdates).toBeGreaterThan(0);
  });

  it("updates an EXISTING mission's status on mission.started", () => {
    // First create the mission
    useStore.getState().ingest(
      envelope("mission.created", { id: "m-2", title: "Test", status: "created", created_at: new Date().toISOString() })
    );
    // Then start it
    useStore.getState().ingest(
      envelope("mission.started", { id: "m-2", title: "Test", status: "executing", created_at: new Date().toISOString() })
    );
    expect(useStore.getState().missions["m-2"].status).toBe("executing");
  });

  it("preserves mission fields across multiple lifecycle events", () => {
    useStore.getState().ingest(
      envelope("mission.created", {
        id: "m-3", title: "Original", description: "Original desc",
        status: "created", priority: "high", created_at: new Date().toISOString(),
      })
    );
    // mission.planned event may not include all fields — must not lose them
    useStore.getState().ingest(
      envelope("mission.planned", { id: "m-3", status: "planned" })
    );
    const m = useStore.getState().missions["m-3"];
    expect(m.title).toBe("Original");       // preserved
    expect(m.description).toBe("Original desc");  // preserved
    expect(m.status).toBe("planned");        // updated
  });
});

// ── Phase 15: Ecosystem event ingestion ──────────────────────────────────
describe("ecosystem events", () => {
  beforeEach(() => {
    useStore.setState({ ecosystem: null });
  });

  it("ingests ecosystem.statistics.updated into the ecosystem snapshot", () => {
    useStore.getState().ingest(
      envelope("ecosystem.statistics.updated", {
        total_runtimes: 5,
        healthy_runtimes: 4,
        unique_capabilities: 7,
      })
    );
    const eco = useStore.getState().ecosystem;
    expect(eco).not.toBeNull();
    expect(eco!.stats).toEqual({ total_runtimes: 5, healthy_runtimes: 4, unique_capabilities: 7 });
    expect(eco!.lastEventAt).toBeGreaterThan(0);
  });

  it("ingests ecosystem.health.updated into the health slice", () => {
    useStore.getState().ingest(
      envelope("ecosystem.health.updated", {
        level: "healthy",
        health_score: 0.82,
      })
    );
    const eco = useStore.getState().ecosystem;
    expect(eco).not.toBeNull();
    expect(eco!.health).toEqual({ level: "healthy", health_score: 0.82 });
    expect(eco!.stats).toBeNull();
  });

  it("ingests ecosystem.capability.updated into graphStats", () => {
    useStore.getState().ingest(
      envelope("ecosystem.capability.updated", { total_nodes: 12, total_edges: 24 })
    );
    expect(useStore.getState().ecosystem?.graphStats).toEqual({ total_nodes: 12, total_edges: 24 });
  });

  it("ingests ecosystem.collaboration.updated into networkStats", () => {
    useStore.getState().ingest(
      envelope("ecosystem.collaboration.updated", { total_links: 3, average_trust: 0.7 })
    );
    expect(useStore.getState().ecosystem?.networkStats).toEqual({ total_links: 3, average_trust: 0.7 });
  });

  it("preserves existing slices across different ecosystem events", () => {
    useStore.getState().ingest(envelope("ecosystem.statistics.updated", { total_runtimes: 1 }));
    useStore.getState().ingest(envelope("ecosystem.health.updated", { level: "optimal" }));
    useStore.getState().ingest(envelope("ecosystem.capability.updated", { total_nodes: 5 }));
    const eco = useStore.getState().ecosystem;
    expect(eco!.stats).toEqual({ total_runtimes: 1 });
    expect(eco!.health).toEqual({ level: "optimal" });
    expect(eco!.graphStats).toEqual({ total_nodes: 5 });
  });
});
