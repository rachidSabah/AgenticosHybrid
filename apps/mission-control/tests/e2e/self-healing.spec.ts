import { test, expect } from "@playwright/test";

// Honest-mode E2E (spec absolute rule: no fabricated repair results).
//
// Without a backend, "Run System Check" can only report locally observable
// facts (e.g. the disconnected EventBus WebSocket), and "Repair All" cannot
// repair anything — the view must keep the issues unresolved and say so
// instead of inventing "0 unresolved issues".
test.describe("Self-Healing Infrastructure E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    // Relative URL — works on any port (static serve, dev server, or preview).
    await page.goto("/");
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

  test("2. system check offline detects real issues; Repair All cannot fake success", async ({ page }) => {
    const checkBtn = page.locator("button:has-text('Run System Check')");
    await checkBtn.click();

    // Offline, the locally observable fact is the disconnected EventBus
    // WebSocket — it must be reported as an unresolved issue.
    await expect(
      page.getByText("EventBus WebSocket disconnected", { exact: false })
    ).toBeVisible({ timeout: 15000 });

    const repairBtn = page.locator("button:has-text('Repair All')");
    await repairBtn.click();

    // No backend: the repair must NOT run, the view must say so…
    await expect(
      page.getByText("Repair All did NOT run", { exact: false })
    ).toBeVisible({ timeout: 15000 });

    // …and the detected issue must remain unresolved — never a fabricated
    // "0 unresolved / No active issues" success state.
    await expect(
      page.getByText("EventBus WebSocket disconnected", { exact: false })
    ).toBeVisible();
    await expect(page.getByText("No active issues")).toHaveCount(0);
  });
});
