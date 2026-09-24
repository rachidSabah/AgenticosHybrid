import { test, expect } from "@playwright/test";

// Honest-mode E2E (spec absolute rule: nothing fabricated).
//
// CI serves the static export WITHOUT a backend, so no journal exists and no
// fork can be recorded. These tests assert the HONEST offline behavior: the
// Counterfactual Lab must state that no recorded runs exist and must never
// render a synthetic fork record or a made-up diff.
test.describe("Counterfactual Fork Lab E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const navBtn = page.locator("button:has-text('Counterfactual Lab')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Counterfactual Fork Lab", { timeout: 15000 });
  });

  test("1. shows the honest NO DATA state when no runs are recorded", async ({ page }) => {
    await expect(page.locator("h1:has-text('Counterfactual Fork Lab')")).toBeVisible();
    await expect(page.locator("text=Recorded runs (event journal)")).toBeVisible();
    await expect(page.locator("text=NO DATA — no recorded event streams yet").first()).toBeVisible();
  });

  test("2. fork without a source run explains itself instead of pretending", async ({ page }) => {
    const forkBtn = page.locator("button:has-text('Create fork')").first();
    await expect(forkBtn).toBeVisible();
    await forkBtn.click({ force: true });
    // Honest guidance: the operator is told nothing was forked.
    await expect(page.locator("text=Pick a recorded run first").first()).toBeVisible();
  });
});
