import { test, expect } from "@playwright/test";

// Honest-mode E2E (spec absolute rule: no fabricated chaos results).
//
// The CI frontend job serves the static export WITHOUT a backend, so no real
// fault can be injected and no recovery can be measured. These tests assert
// the HONEST offline behavior: the view must state that nothing was injected,
// keep the "no data" empty states, and never render a fabricated
// "recovered_cleanly" experiment or a synthetic RCA postmortem.
test.describe("Chaos Studio & SRE Canary Simulator E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const navBtn = page.locator("button:has-text('Chaos Studio')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Autonomous Chaos & Resilience Testing Studio", { timeout: 15000 });
  });

  test("1. fault injection without a backend records nothing and says so", async ({ page }) => {
    await expect(page.locator("text=Resilience Score")).toBeVisible();
    await expect(page.locator("text=Autonomous Chaos & Resilience Testing Studio")).toBeVisible();

    // Honest empty state before the attempt.
    await expect(page.locator("text=No experiments run yet")).toBeVisible();

    const injectBtn = page.locator("button:has-text('Inject Fault')");
    await expect(injectBtn).toBeVisible();
    await injectBtn.click();

    // The view must report that the fault was NOT injected…
    await expect(
      page.getByText("fault was NOT injected", { exact: false })
    ).toBeVisible({ timeout: 15000 });

    // …keep the honest empty state (no experiment materialized)…
    await expect(page.locator("text=No experiments run yet")).toBeVisible();

    // …and never fabricate a recovery result.
    await expect(page.getByText("recovered_cleanly")).toHaveCount(0);
    await expect(page.locator("text=Resilience Score")).toBeVisible();
  });

  test("2. canary simulation without a backend records nothing — no synthetic RCA", async ({ page }) => {
    await expect(page.locator("text=Autonomous SRE Canary Simulator")).toBeVisible();
    await expect(page.locator("text=No canary patches")).toBeVisible();

    const canaryBtn = page.locator("button:has-text('Simulate Autonomous Canary Patch')");
    await expect(canaryBtn).toBeVisible();
    await canaryBtn.click();

    // The view must report that no deployment was created…
    await expect(
      page.getByText("canary was NOT deployed", { exact: false })
    ).toBeVisible({ timeout: 15000 });

    // …keep the honest empty state…
    await expect(page.locator("text=No canary patches")).toBeVisible();

    // …and never fabricate an incident ID, RCA postmortem, or rollback action.
    await expect(page.getByText("ROOT CAUSE ANALYSIS (RCA)")).toHaveCount(0);
    // exact:true — the panel SUBTITLE contains "1-click canary rollback" and
    // getByText matches substrings case-insensitively by default.
    await expect(page.getByText("1-Click Canary Rollback", { exact: true })).toHaveCount(0);
  });
});
