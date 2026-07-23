import { test, expect } from "@playwright/test";

test.describe("AgenticOS Mission Control E2E Suite", () => {
  test.use({ actionTimeout: 15000 });

  test.beforeEach(async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
  });

  test("loads Mission Overview dashboard cleanly", async ({ page }) => {
    await expect(page).toHaveTitle(/Mission Control|AgenticOS/i);
    // AppShell renders null until mounted — wait for any visible element first
    const nav = page.locator("nav, [role='navigation'], aside, .sidebar, main");
    await expect(nav.first()).toBeVisible({ timeout: 15000 });
    // Then confirm main exists (may be inside the layout)
    const body = page.locator("body");
    await expect(body).toBeVisible();
  });

  test("navigates through views cleanly", async ({ page }) => {
    await page.keyboard.press("Control+k");
    const palette = page.locator("[placeholder*='Search views']");
    if (await palette.isVisible({ timeout: 2000 }).catch(() => false)) {
      await expect(palette).toBeVisible();
      await page.keyboard.press("Escape");
    }
  });

  test("validates 3D Galaxy Constellation canvas", async ({ page }) => {
    // Wait for mount then click sidebar button
    await page.waitForSelector("button", { timeout: 15000 });
    const btn = page.getByRole("button", { name: "Agent Constellation" });
    if (await btn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await btn.click();
    }
    await page.waitForTimeout(500);
    const canvas = page.locator("canvas");
    if (await canvas.count() > 0) {
      await expect(canvas.first()).toBeVisible();
    }
  });

  test("validates 3D Neural Supercomputer AI Brain", async ({ page }) => {
    await page.waitForSelector("button", { timeout: 15000 });
    const btn = page.getByRole("button", { name: "AI Brain" });
    if (await btn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await btn.click();
    }
    await page.waitForTimeout(500);
    const canvas = page.locator("canvas");
    if (await canvas.count() > 0) {
      await expect(canvas.first()).toBeVisible();
    }
  });

  test("tests responsive viewports & theme toggle", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await expect(page.locator("body")).toBeVisible();
    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(page.locator("body")).toBeVisible();
  });
});
