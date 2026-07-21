import { describe, it, expect } from "vitest";

/**
 * E2E smoke test — verifies that the core Mission Control modules
 * import and their public interfaces are type-correct.
 *
 * These tests run in a jsdom environment and validate that:
 *   - All views export components
 *   - All store slices are accessible
 *   - API client methods exist
 */

describe("Mission Control — E2E Smoke", () => {
  it("library imports resolve", async () => {
    const { api } = await import("@/lib/api");
    expect(api).toBeDefined();
    expect(typeof api.missions).toBe("function");
    expect(typeof api.discoveryProviders).toBe("function");
    expect(typeof api.health).toBe("function");
    expect(typeof api.providers).toBe("function");
  });

  it("store exports slices", async () => {
    const { useStore } = await import("@/lib/store");
    const state = useStore.getState();
    expect(state).toBeDefined();
    expect(Array.isArray(state.events)).toBe(true);
    expect(typeof state.connected).toBe("boolean");
    expect(typeof state.setMissions).toBe("function");
  });

  it("core types exist", async () => {
    const t = await import("@/lib/types");
    // Check the module exports key types
    expect(t).toBeDefined();
  });

  it("all views export a matching component", async () => {
    const viewModules = [
      { path: "@/views/mission-overview", name: "MissionOverview" },
      { path: "@/views/ai-brain", name: "AiBrain" },
      { path: "@/views/agent-constellation", name: "AgentConstellation" },
      { path: "@/views/mission-orchestrator", name: "MissionOrchestrator" },
      { path: "@/views/discovery-dashboard", name: "DiscoveryDashboard" },
      { path: "@/views/self-healing", name: "SelfHealingPanel" },
      { path: "@/views/provider-control-center", name: "ProviderControlCenter" },
      { path: "@/views/system-monitor", name: "SystemMonitor" },
      { path: "@/views/desktop-diagnostics", name: "DesktopDiagnostics" },
    ];

    for (const { path, name } of viewModules) {
      const mod = await import(path);
      expect(mod[name]).toBeDefined();
    }
  });
});
