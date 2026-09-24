import { test, expect } from "@playwright/test";

// Honest-mode E2E (spec absolute rule: nothing fabricated).
//
// CI serves the static export WITHOUT a backend, so no pending approvals
// exist and none can be created. These tests assert the HONEST offline
// behavior: the view states the service is unavailable and never renders a
// synthetic pending approval, a fake token, or a made-up audit trail.
test.describe("Mobile Approvals E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const navBtn = page.locator("button:has-text('Mobile Approvals')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Mobile Approvals", { timeout: 15000 });
  });

  test("1. shows the honest NO DATA state when the service is unavailable", async ({ page }) => {
    await expect(page.locator("h1:has-text('Mobile Approvals')")).toBeVisible();
    await expect(page.locator("text=Pending decisions")).toBeVisible();
    await expect(
      page.locator("text=NO DATA — nothing is waiting for a human right now").first()
    ).toBeVisible();
  });

  test("2. no approval can be faked: no history and no audit entries appear", async ({ page }) => {
    await expect(
      page.locator("text=NO DATA — no approval requests yet").first()
    ).toBeVisible();
    await expect(
      page.locator("text=NO DATA — no approval transitions yet").first()
    ).toBeVisible();
  });
});
