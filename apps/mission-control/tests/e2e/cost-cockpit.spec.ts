import { test, expect } from "@playwright/test";

// Honest-mode E2E (spec absolute rule: nothing fabricated).
//
// CI serves the static export WITHOUT a backend, so no cost events exist and
// no summary can be loaded. These tests assert the HONEST offline behavior:
// the cockpit says cost data is unavailable and never renders a synthetic
// total, a fake breakdown, or an invented forecast.
test.describe("Cost Cockpit E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const navBtn = page.locator("button:has-text('Cost Cockpit')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Cost Cockpit", { timeout: 15000 });
  });

  test("1. shows the honest NO DATA state when costs cannot be loaded", async ({ page }) => {
    await expect(page.locator("h1:has-text('Cost Cockpit')")).toBeVisible();
    await expect(
      page.locator("text=NO DATA — cost totals cannot be loaded").first()
    ).toBeVisible();
  });

  test("2. nothing is invented: no totals, no breakdowns, no forecast", async ({ page }) => {
    await expect(page.locator("text=Measured spend")).toHaveCount(0);
    await expect(page.locator("text=By agent")).toHaveCount(0);
    await expect(page.locator("text=forecast method:")).toHaveCount(0);
  });
});
