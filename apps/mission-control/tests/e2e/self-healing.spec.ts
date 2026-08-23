import { test, expect } from "@playwright/test";

test.describe("Self-Healing Infrastructure E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("http://localhost:3000");
    await page.waitForSelector("main, [data-layout='main']", { timeout: 15000 });
    
    // Navigate to Self-Healing via shortcut H or sidebar
    await page.keyboard.press("h");
    await page.waitForTimeout(1000);
  });

  test("1. validates Self-Healing header and control deck", async ({ page }) => {
    const heading = page.locator("h1:has-text('Self-Healing Infrastructure')");
    await expect(heading).toBeVisible({ timeout: 10000 });
    
    const badge = page.locator("text=Autonomous SRE");
    await expect(badge).toBeVisible();

    await expect(page.locator("button:has-text('Run System Check')")).toBeVisible();
    await expect(page.locator("button:has-text('Repair All')")).toBeVisible();
  });

  test("2. executes Run System Check and triggers Repair All to achieve 0 unresolved issues", async ({ page }) => {
    const checkBtn = page.locator("button:has-text('Run System Check')");
    await checkBtn.click();
    await page.waitForTimeout(2000);

    const repairBtn = page.locator("button:has-text('Repair All')");
    await repairBtn.click();
    await page.waitForTimeout(2000);

    // Verify unresolved issues count is 0
    await expect(page.locator("text=0 unresolved")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("text=No active issues")).toBeVisible();
  });
});