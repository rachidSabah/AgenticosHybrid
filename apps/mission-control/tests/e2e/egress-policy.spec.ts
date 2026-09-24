import { test, expect } from "@playwright/test";

// Honest-mode E2E (spec absolute rule: nothing fabricated).
//
// CI serves the static export WITHOUT a backend, so the policy cannot be
// loaded and no verdict or report can be produced. These tests assert the
// HONEST offline behavior: the view says what is unavailable and never
// renders a synthetic policy, a fabricated redaction report, or a made-up
// verdict.
test.describe("Egress Policy E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const navBtn = page.locator("button:has-text('Egress Policy')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Egress Policy", { timeout: 15000 });
  });

  test("1. shows the honest NO DATA state when the policy cannot be loaded", async ({ page }) => {
    await expect(page.locator("h1:has-text('Egress Policy')")).toBeVisible();
    await expect(
      page.locator("text=NO DATA — the policy could not be loaded").first()
    ).toBeVisible();
  });

  test("2. interactive policy surfaces are hidden when the backend is unreachable", async ({
    page,
  }) => {
    // Honest behavior: no editor, no inspector, no verdict buttons — nothing
    // that could pretend to apply or test a policy that was never loaded.
    await expect(page.getByRole("button", { name: "Inspect", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Redact", exact: true })).toHaveCount(0);
    await expect(page.locator("text=Policy switches (persisted on change)")).toHaveCount(0);
    // The only thing offered is the real diagnosis.
    await expect(
      page.locator("text=Egress policy unavailable:").first()
    ).toBeVisible();
  });
});
