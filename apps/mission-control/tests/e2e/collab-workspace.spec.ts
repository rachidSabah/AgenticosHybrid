import { test, expect } from "@playwright/test";

test.describe("Collaborative VFS & Voice Command Dispatch E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    
    const navBtn = page.locator("button:has-text('Collaborative VFS')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Monorepo AST Virtual File System (VFS)", { timeout: 15000 });
  });

  test("1. validates multiplayer cursor presence and AST tree exploration", async ({ page }) => {
    await expect(page.locator("text=Active Multiplayer Cursors")).toBeVisible();
    await expect(page.locator("text=Indexed AST Symbols")).toBeVisible();
    await expect(page.locator("text=Monorepo AST Virtual File System (VFS)")).toBeVisible();
    await expect(page.locator("text=Principal Engineer (You)")).toBeVisible();
  });

  test("2. triggers Voice Command Dispatch and validates transcript synthesis", async ({ page }) => {
    const voiceBtn = page.locator("button", { hasText: "Voice Command Dispatch" });
    await expect(voiceBtn).toBeVisible();
    await voiceBtn.click();

    await expect(page.locator("text=Voice Command Transcripts")).toBeVisible();
    await expect(page.locator("main")).toContainText("AgenticOS, run full regression check", { timeout: 10000 });
  });
});