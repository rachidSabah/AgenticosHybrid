import { test, expect } from "@playwright/test";

// Honest-mode E2E (spec absolute rule: nothing fabricated).
//
// CI serves the static export WITHOUT a backend, so no control groups and no
// package store exist. These tests assert the HONEST offline behavior: the
// view states what is unavailable and never renders synthetic usage numbers,
// a fake installed package, or invented journal entries.
test.describe("Agent Cgroups & Packages E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const navBtn = page.locator("button:has-text('Agent Cgroups & Packages')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Agent Cgroups & Packages", { timeout: 15000 });
  });

  test("1. shows the honest NO DATA state with no control groups", async ({ page }) => {
    await expect(page.locator("h1:has-text('Agent Cgroups & Packages')")).toBeVisible();
    await expect(page.locator("text=Control groups (measured usage)")).toBeVisible();
    await expect(
      page.locator("text=NO DATA — no control groups yet").first()
    ).toBeVisible();
  });

  test("2. quota without an agent id explains itself instead of pretending", async ({ page }) => {
    const applyBtn = page.locator("button:has-text('Apply quota')").first();
    await expect(applyBtn).toBeVisible();
    await applyBtn.click({ force: true });
    await expect(
      page.locator("text=Pick an agent id — a quota without an agent enforces nothing").first()
    ).toBeVisible();
  });

  test("3. empty package store and journal are stated honestly", async ({ page }) => {
    await expect(page.locator("text=NO DATA — nothing installed yet").first()).toBeVisible();
    await expect(
      page.locator("text=NO DATA — no package actions recorded yet").first()
    ).toBeVisible();
  });

  test("4. packaging without a source directory reports the real refusal", async ({ page }) => {
    // exact match: the nav button "Agent Cgroups & Packages" also contains
    // the substring "Pack", so a loose :has-text() selector would hit it first
    const packBtn = page.getByRole("button", { name: "Pack", exact: true });
    await expect(packBtn).toBeVisible();
    await packBtn.click();
    // The view shows the real refusal — never a fabricated package.
    await expect(
      page
        .locator("text=Pack failed:")
        .or(page.locator("text=Pack refused:"))
        .first()
    ).toBeVisible({ timeout: 15000 });
  });
});
