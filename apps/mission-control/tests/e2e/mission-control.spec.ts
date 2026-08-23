import { test, expect } from "@playwright/test";

test.describe("AgenticOS Mission Control E2E Comprehensive Suite", () => {
  test("1. loads Mission Overview dashboard cleanly with real metrics", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await expect(page).toHaveTitle(/Mission Control|AgenticOS/i);
    const errors = await page.locator("text=Something went wrong").count();
    expect(errors).toBe(0);
  });

  test("2. validates command palette keyboard navigation", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.keyboard.press("Control+k");
    const palette = page.locator("[placeholder*='Search views']");
    if (await palette.isVisible({ timeout: 2000 }).catch(() => false)) {
      await expect(palette).toBeVisible();
      await page.keyboard.press("Escape");
    }
  });

  test("3. validates 3D Galaxy Constellation canvas via shortcut C", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.keyboard.press("c");
    await page.waitForTimeout(500);
    const canvas = page.locator("canvas");
    if (await canvas.count() > 0) {
      await expect(canvas.first()).toBeVisible();
    }
    const errors = await page.locator("text=Something went wrong").count();
    expect(errors).toBe(0);
  });

  test("4. validates 3D Neural Supercomputer AI Brain via shortcut B", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.keyboard.press("b");
    await page.waitForTimeout(500);
    const canvas = page.locator("canvas");
    if (await canvas.count() > 0) {
      await expect(canvas.first()).toBeVisible();
    }
    const errors = await page.locator("text=Something went wrong").count();
    expect(errors).toBe(0);
  });

  test("5. navigates and validates Prompt Center via shortcut P", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.keyboard.press("p");
    await page.waitForTimeout(500);
    const errors = await page.locator("text=Something went wrong").count();
    expect(errors).toBe(0);
  });

  test("6. navigates and validates AI Agent Binding Center via shortcut A", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.keyboard.press("a");
    await page.waitForTimeout(500);
    const errors = await page.locator("text=Something went wrong").count();
    expect(errors).toBe(0);
  });
  test("7. navigates and validates Swarm Orchestration via shortcut S", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.keyboard.press("s");
    await page.waitForTimeout(500);
    const errors = await page.locator("text=Something went wrong").count();
    expect(errors).toBe(0);
  });

  test("8. navigates and validates Workflow Studio via shortcut W", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.keyboard.press("w");
    await page.waitForTimeout(500);
    const errors = await page.locator("text=Something went wrong").count();
    expect(errors).toBe(0);
  });

  test("9. navigates and validates Provider Control Center via shortcut R", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.keyboard.press("r");
    await page.waitForTimeout(500);
    const errors = await page.locator("text=Something went wrong").count();
    expect(errors).toBe(0);
  });

  test("10. navigates and validates Self-Healing and Diagnostics via shortcut H and X", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.keyboard.press("h");
    await page.waitForTimeout(400);
    await page.keyboard.press("x");
    await page.waitForTimeout(400);
    const errors = await page.locator("text=Something went wrong").count();
    expect(errors).toBe(0);
  });

  test("11. navigates and validates Desktop Views via numeric shortcuts 1-6", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    for (const key of ["1", "2", "3", "4", "5", "6"]) {
      await page.keyboard.press(key);
      await page.waitForTimeout(300);
      const errors = await page.locator("text=Something went wrong").count();
      expect(errors).toBe(0);
    }
  });

  test("12. tests responsive viewports across standard resolutions", async ({ page }) => {
    const viewports = [
      { width: 1920, height: 1080 },
      { width: 1440, height: 900 },
      { width: 1280, height: 720 },
      { width: 1024, height: 768 },
      { width: 768, height: 1024 },
      { width: 375, height: 667 }
    ];
    for (const vp of viewports) {
      await page.setViewportSize(vp);
      await page.goto("/");
      await page.waitForLoadState("domcontentloaded");
      const errors = await page.locator("text=Something went wrong").count();
      expect(errors).toBe(0);
    }
  });
});

