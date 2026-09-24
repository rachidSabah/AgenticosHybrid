import { test, expect } from "@playwright/test";

// Honest-mode E2E (spec absolute rule: no fabricated hardware/model data).
//
// Without a backend the GPU hub has NO telemetry and NO registered models.
// The view must render "—" placeholders and the explicit "No models detected"
// empty state — it must never show a synthetic model catalog.
//
// GPU telemetry additionally requires real hardware — skip in CI, where no
// GPU exists (an honest skip, not a simulated pass).
const isCI = !!process.env.CI;

test.describe("Local GPU Hub & AI Hardware Acceleration E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(isCI, "Requires real GPU hardware — skipped in CI");
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const navBtn = page.locator("button:has-text('Local AI / GPU')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Zero-Config Local Model Hub", { timeout: 15000 });
  });

  test("1. shows honest telemetry placeholders and no invented model catalog", async ({ page }) => {
    await expect(page.locator("text=Hardware Acceleration")).toBeVisible();
    await expect(page.locator("text=VRAM Allocated")).toBeVisible();
    await expect(page.locator("text=GPU Temperature")).toBeVisible();

    // Without a backend no model has registered — the honest empty state
    // must be shown, and the removed fabricated catalog must stay gone.
    await expect(page.locator("text=No models detected")).toBeVisible();
    await expect(page.getByText("DeepSeek Coder 6.7B")).toHaveCount(0);
    await expect(page.getByText("Qwen 2.5 Coder 7B")).toHaveCount(0);

    // Toggle offline mode — control exists and stays interactive.
    const offlineBtn = page.locator("button:has-text('Enable Offline'), button:has-text('Disable')");
    await expect(offlineBtn).toBeVisible();
    await offlineBtn.click();
    await page.waitForTimeout(1000);
  });
});
