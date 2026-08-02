#!/usr/bin/env npx tsx
/**
 * Screenshot Generator — captures all Mission Control views using Playwright.
 *
 * Usage:
 *   npm --prefix tools/screenshots install
 *   npx tsx tools/screenshots/generate.ts
 */

import { chromium } from "playwright";
import * as fs from "fs";
import * as path from "path";
import { spawn, type ChildProcess } from "child_process";

const FRONTEND_URL = "http://localhost:3000";
const SCREENSHOTS_DIR = path.resolve(__dirname, "../../docs/screenshots");
const VIEWPORT = { width: 1920, height: 1080 };

const VIEWS = [
  // Core views
  { id: "overview", name: "Mission Overview" },
  { id: "brain", name: "AI Brain" },
  { id: "constellation", name: "Agent Constellation" },
  { id: "execution", name: "Execution Graph" },
  { id: "workflow", name: "Workflow Studio" },
  { id: "pipeline", name: "Pipeline Builder" },
  { id: "providers", name: "Provider Control Center" },
  { id: "memory", name: "Memory Explorer" },
  { id: "plugins", name: "Plugin Marketplace" },
  { id: "mcp", name: "MCP Manager" },
  { id: "workspace", name: "Workspace Explorer" },
  { id: "timeline", name: "Task Timeline" },
  { id: "monitor", name: "System Monitor" },
  { id: "discovery", name: "Discovery Dashboard" },
  { id: "swarm", name: "Swarm Dashboard" },
  // Desktop views (M6)
  { id: "desktop-overview", name: "Desktop Overview" },
  { id: "desktop-runtimes", name: "Desktop Runtimes" },
  { id: "desktop-updates", name: "Desktop Updates" },
  { id: "desktop-diagnostics", name: "Desktop Diagnostics" },
  { id: "desktop-offline", name: "Offline Mode" },
  { id: "desktop-settings", name: "Desktop Settings" },
];

async function waitForServer(url: string, timeout = 30000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`Server at ${url} did not start within ${timeout}ms`);
}

async function startProcess(cmd: string, args: string[], cwd: string, label: string): Promise<ChildProcess> {
  const proc = spawn(cmd, args, { cwd, stdio: "pipe", shell: true });
  proc.stdout?.on("data", (d) => process.stdout.write(`[${label}] ${d}`));
  proc.stderr?.on("data", (d) => process.stderr.write(`[${label}] ${d}`));
  return proc;
}

async function main() {
  console.log("=== AgenticOS Screenshot Generator ===");

  // Ensure directory exists
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

  // Start backend
  console.log("\n[1/4] Starting backend...");
  const backend = await startProcess("uv", ["run", "python", "-m", "agentic_os", "serve"], process.cwd(), "backend");
  await waitForServer("http://localhost:8000/healthz");
  console.log("  Backend ready.");

  // Start frontend
  console.log("\n[2/4] Starting frontend...");
  const frontend = await startProcess("npm", ["run", "dev"], path.resolve(__dirname, "../../apps/mission-control"), "frontend");
  await waitForServer("http://localhost:3000");
  console.log("  Frontend ready.");

  // Launch browser
  console.log("\n[3/4] Launching browser...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: VIEWPORT });
  const page = await context.newPage();

  // Take screenshots
  console.log("\n[4/4] Capturing screenshots...");
  for (const view of VIEWS) {
    console.log(`  [${view.id}] ${view.name}...`);
    try {
      await page.goto(`${FRONTEND_URL}/?view=${view.id}`, { waitUntil: "networkidle" });
      await page.waitForTimeout(2000); // Wait for lazy-loaded components

      // Light theme variant for first view
      const themeSuffix = view.id === "overview" ? "-dark" : "";

      await page.screenshot({
        path: path.join(SCREENSHOTS_DIR, `${view.id}${themeSuffix}.png`),
        fullPage: false,
      });

      // Also take a light theme screenshot for the overview
      if (view.id === "overview") {
        await page.evaluate(() => {
          document.documentElement.classList.remove("dark");
          document.documentElement.classList.add("light");
        });
        await page.waitForTimeout(500);
        await page.screenshot({
          path: path.join(SCREENSHOTS_DIR, "overview-light.png"),
          fullPage: false,
        });
        // Switch back to dark
        await page.evaluate(() => {
          document.documentElement.classList.remove("light");
          document.documentElement.classList.add("dark");
        });
      }

      console.log(`    Saved ${view.id}.png`);
    } catch (err) {
      console.error(`    Failed: ${err}`);
    }
  }

  // Cleanup
  await browser.close();
  backend.kill();
  frontend.kill();

  console.log("\n=== Screenshot generation complete ===");
  console.log(`Screenshots saved to: ${SCREENSHOTS_DIR}`);
}

main().catch(console.error);
