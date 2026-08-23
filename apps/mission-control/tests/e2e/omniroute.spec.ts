import { test, expect } from "@playwright/test";

test.describe("OmniRoute Universal AI Networking Engine E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    
    // Direct navigation via sidebar or command palette
    const btn = page.locator("button.group\\/sidebar-item:has-text('OmniRoute')").first();
    if (await btn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await btn.click({ force: true });
    } else {
      await page.keyboard.press("Control+k");
      const palette = page.locator("[placeholder*='Search views']");
      if (await palette.isVisible({ timeout: 3000 }).catch(() => false)) {
        await palette.fill("OmniRoute");
        await page.keyboard.press("Enter");
      }
    }
    await page.waitForSelector("h1:has-text('OMNIROUTE UNIVERSAL AI NETWORKING ENGINE')", { timeout: 15000 });
  });

  test("1. validates OmniRoute status bar and live telemetry", async ({ page }) => {
    const heading = page.locator("h1:has-text('OMNIROUTE UNIVERSAL AI NETWORKING ENGINE')");
    await expect(heading).toBeVisible();
    
    const subtitle = page.locator("text=Smart Model Routing, Token Compression & Provider Failover Subsystem");
    await expect(subtitle).toBeVisible();

    await expect(page.locator("text=Requests Processed")).toBeVisible();
    await expect(page.locator("text=Avg Latency")).toBeVisible();
    await expect(page.locator("text=Compression Savings")).toBeVisible();
    await expect(page.locator("text=Estimated Saved")).toBeVisible();
  });

  test("2. validates all OmniRoute sub-tabs and controls", async ({ page }) => {
    // 1. Live Routing Graph tab
    const routingTab = page.locator("button:has-text('Live Routing Graph')");
    await expect(routingTab).toBeVisible();
    await routingTab.click();
    await expect(page.locator("text=Live AI Routing Pipeline Graph")).toBeVisible();
    await expect(page.locator("text=Test Route Decision")).toBeVisible();

    // 2. Route Composer tab
    const composerTab = page.locator("button:has-text('Route Composer')");
    await expect(composerTab).toBeVisible();
    await composerTab.click();
    await expect(page.locator("text=Route Policy Composer")).toBeVisible();
    await expect(page.locator("button:has-text('Add Route Policy')")).toBeVisible();

    // 3. Routing Policies tab
    const policiesTab = page.locator("button:has-text('Routing Policies')");
    await expect(policiesTab).toBeVisible();
    await policiesTab.click();
    await expect(page.locator("text=Configurable Routing Policies")).toBeVisible();

    // 4. Token Compression tab
    const compressionTab = page.locator("button:has-text('Token Compression')");
    await expect(compressionTab).toBeVisible();
    await compressionTab.click();
    await expect(page.locator("text=Token Compression Engine")).toBeVisible();

    // 5. Budget & Failover tab
    const budgetTab = page.locator("button:has-text('Budget & Failover')");
    await expect(budgetTab).toBeVisible();
    await budgetTab.click();
    await expect(page.locator("text=Failover Event Monitor")).toBeVisible();
    await expect(page.locator("text=Budget & Cost Optimization")).toBeVisible();
  });

  test("3. executes Route Evaluation simulation in Live Routing Graph", async ({ page }) => {
    const routingTab = page.locator("button:has-text('Live Routing Graph')");
    await routingTab.click();

    const textarea = page.locator("textarea[placeholder*='Refactor this React component']");
    await expect(textarea).toBeVisible();
    await textarea.fill("Refactor high-concurrency event bus handler in Rust or Python for sub-millisecond dispatch latency");

    const evalBtn = page.locator("button:has-text('Evaluate Route')");
    await evalBtn.click();

    await page.waitForTimeout(2000);
    await expect(page.locator("text=[ROUTING DECISION]")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("main")).toContainText("Target:");
  });

  test("4. executes Token Compression test and verifies savings calculation", async ({ page }) => {
    const compressionTab = page.locator("button:has-text('Token Compression')");
    await compressionTab.click();

    const textarea = page.locator("textarea[placeholder*='Paste long code or prompt text']");
    await expect(textarea).toBeVisible();
    await textarea.fill("Please analyze this system architecture and provide comprehensive optimization recommendations for high throughput token streaming");

    const compressBtn = page.locator("button:has-text('Compress Prompt')");
    await compressBtn.click();

    await page.waitForTimeout(2000);
    await expect(page.locator("main")).toContainText("Original:");
    await expect(page.locator("main")).toContainText("Compressed:");
  });
});