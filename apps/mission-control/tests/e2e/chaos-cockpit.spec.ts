import { test, expect } from "@playwright/test";

test.describe("Chaos Studio & SRE Canary Simulator E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    
    const navBtn = page.locator("button:has-text('Chaos Studio')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Autonomous Chaos & Resilience Testing Studio", { timeout: 15000 });
  });

  test("1. executes live Chaos fault injection experiment", async ({ page }) => {
    await expect(page.locator("text=Resilience Score")).toBeVisible();
    await expect(page.locator("text=Autonomous Chaos & Resilience Testing Studio")).toBeVisible();

    const injectBtn = page.locator("button:has-text('Inject Fault')");
    await expect(injectBtn).toBeVisible();
    await injectBtn.click();

    await page.waitForTimeout(2000);
    await expect(page.locator("main")).toContainText("recovered_cleanly");
  });

  test("2. validates Autonomous SRE Canary Simulator and 1-Click Rollback", async ({ page }) => {
    await expect(page.locator("text=Autonomous SRE Canary Simulator")).toBeVisible();

    const canaryBtn = page.locator("button:has-text('Simulate Autonomous Canary Patch')");
    await expect(canaryBtn).toBeVisible();
    await canaryBtn.click();

    await page.waitForTimeout(2000);
    await expect(page.locator("main")).toContainText("ROOT CAUSE ANALYSIS (RCA)");
    await expect(page.locator("button:has-text('1-Click Canary Rollback')").first()).toBeVisible();
  });
});