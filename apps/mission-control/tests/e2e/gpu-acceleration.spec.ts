import { test, expect } from "@playwright/test";

test.describe("Local GPU Hub & AI Hardware Acceleration E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    
    const navBtn = page.locator("button:has-text('Local AI / GPU')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Zero-Config Local Model Hub", { timeout: 15000 });
  });

  test("1. validates GPU telemetry and local model discovery matrix", async ({ page }) => {
    await expect(page.locator("text=Hardware Acceleration")).toBeVisible();
    await expect(page.locator("text=VRAM Allocated")).toBeVisible();
    await expect(page.locator("text=GPU Temperature")).toBeVisible();
    await expect(page.locator("text=DeepSeek Coder 6.7B")).toBeVisible();
    await expect(page.locator("text=Qwen 2.5 Coder 7B")).toBeVisible();

    // Toggle offline mode
    const offlineBtn = page.locator("button:has-text('Enable Offline'), button:has-text('Disable')");
    await expect(offlineBtn).toBeVisible();
    await offlineBtn.click();
    await page.waitForTimeout(1000);
  });
});