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
});
