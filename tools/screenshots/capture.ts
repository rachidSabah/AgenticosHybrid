import { chromium } from "playwright";
import * as fs from "fs";
import * as path from "path";

const FRONTEND_URL = "http://localhost:3000";
const SCREENSHOTS_DIR = path.resolve(__dirname, "../../docs/screenshots");
const VIEWPORT = { width: 1920, height: 1080 };

const PAGES = [
  { id: "mission-overview", url: "/", name: "Mission Overview" },
  { id: "dashboard", url: "/dashboard", name: "Dashboard" },
  { id: "providers", url: "/providers", name: "Providers" },
  { id: "execution", url: "/execution", name: "Execution" },
  { id: "swarm", url: "/swarm", name: "Swarm" },
  { id: "mcp", url: "/mcp", name: "MCP" },
  { id: "plugins", url: "/plugins", name: "Plugins" },
  { id: "desktop", url: "/desktop", name: "Desktop" },
  { id: "updates", url: "/updates", name: "Updates" },
  { id: "diagnostics", url: "/diagnostics", name: "Diagnostics" },
  { id: "performance", url: "/performance", name: "Performance" },
  { id: "memory", url: "/memory", name: "Memory" },
  { id: "security", url: "/security", name: "Security" },
  { id: "logs", url: "/logs", name: "Logs" },
  { id: "settings", url: "/settings", name: "Settings" },
];

async function main() {
  console.log("=== AgenticOS Screenshot Capture ===");
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

  console.log("\n[1/2] Launching browser...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: VIEWPORT });
  const page = await context.newPage();

  console.log("[2/2] Capturing screenshots...");
  for (const p of PAGES) {
    process.stdout.write(`  [${p.id}] ${p.name}...`);
    try {
      await page.goto(`${FRONTEND_URL}${p.url}`, { waitUntil: "load", timeout: 10000 });
      await page.waitForTimeout(3000);
      await page.screenshot({
        path: path.join(SCREENSHOTS_DIR, `${p.id}.png`),
        fullPage: false,
      });
      console.log(" OK");
    } catch (err) {
      console.log(` FAILED: ${err}`);
    }
  }

  await browser.close();
  console.log(`\n=== Complete: screenshots saved to ${SCREENSHOTS_DIR} ===`);
}

main().catch(console.error);
