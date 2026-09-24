import { test, expect } from "@playwright/test";

// Updated for the forensic remediation: the collaborative workspace no longer
// fabricates presence rows, demo file trees, or synthetic voice transcripts.
test.describe("Collaborative VFS & Voice Command Dispatch E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const navBtn = page.locator("button:has-text('Collaborative VFS')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Monorepo AST Virtual File System (VFS)", { timeout: 15000 });
  });

  test("1. shows honest presence + AST empty states (no fabricated rows)", async ({ page }) => {
    await expect(page.locator("text=Active Multiplayer Cursors")).toBeVisible();
    await expect(page.locator("text=Indexed AST Symbols")).toBeVisible();
    await expect(page.locator("text=Monorepo AST Virtual File System (VFS)")).toBeVisible();
    // The fake "Principal Engineer (You)" presence row was removed — the
    // panel must show an honest empty state instead of invented cursors.
    await expect(page.locator("text=Principal Engineer (You)")).toHaveCount(0);
  });

  test("2. voice dispatch does NOT fabricate a transcript", async ({ page }) => {
    const voiceBtn = page.locator("button", { hasText: "Voice Command Dispatch" });
    await expect(voiceBtn).toBeVisible();
    await voiceBtn.click();

    // The canned "AgenticOS, run full regression check..." transcript was
    // removed; the dispatcher reports honestly that nothing was transcribed.
    await expect(page.locator("text=Voice Command Transcripts")).toBeVisible();
    await expect(page.locator("main")).not.toContainText("run full regression check on all subsystems", { timeout: 5000 });
  });
});
