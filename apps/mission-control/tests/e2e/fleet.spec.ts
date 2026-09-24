import { test, expect } from "@playwright/test";

// Honest-mode E2E (spec absolute rule: nothing fabricated).
//
// CI serves the static export WITHOUT a backend, so no discovery snapshot
// exists and no dispatch can run. These tests assert the HONEST offline
// behavior: the Agent Fleet must state that the fleet is unavailable / empty
// and must never render a synthetic roster, a fake bid ranking, or a made-up
// dispatch record.
test.describe("Agent Fleet E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const navBtn = page.locator("button:has-text('Agent Fleet')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Agent Fleet", { timeout: 15000 });
  });

  test("1. shows the honest NO DATA state when discovery finds nothing", async ({ page }) => {
    await expect(page.locator("h1:has-text('Agent Fleet')")).toBeVisible();
    await expect(page.locator("text=Fleet roster (live discovery snapshot)")).toBeVisible();
    await expect(page.locator("text=NO DATA — no CLIs in the current discovery snapshot").first()).toBeVisible();
  });

  test("2. bidding without any eligible brain explains itself instead of ranking", async ({ page }) => {
    await page
      .locator("input[placeholder='refactor the auth module']")
      .first()
      .fill("translate the docs");
    const bidBtn = page.locator("button:has-text('Run bid')").first();
    await expect(bidBtn).toBeVisible();
    await bidBtn.click({ force: true });
    // Either the backend answered "no eligible brains" (honest NO DATA) or the
    // request failed and the real error is shown — never a fabricated ranking.
    await expect(
      page
        .locator("text=NO DATA — no active, drivable brain declares the required capabilities")
        .or(page.locator("text=Bid failed:"))
        .first()
    ).toBeVisible({ timeout: 15000 });
  });

  test("3. dispatch without an agent selected explains itself instead of sending", async ({ page }) => {
    const dispatchBtn = page.locator("button:has-text('Dispatch')").first();
    await expect(dispatchBtn).toBeVisible();
    await dispatchBtn.click({ force: true });
    await expect(page.locator("text=Pick an agent to dispatch to").first()).toBeVisible();
  });

  test("4. empty dispatch history is stated honestly", async ({ page }) => {
    await expect(
      page.locator("text=NO DATA — no fleet dispatch has run yet").first()
    ).toBeVisible();
  });
});
