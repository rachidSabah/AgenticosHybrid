import { test, expect } from "@playwright/test";

test.describe("Swarm Studio & Step-Debugger E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    
    const navBtn = page.locator("button:has-text('Swarm Studio')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Interactive Swarm Execution DAG", { timeout: 15000 });
  });

  test("1. validates Swarm DAG nodes and step-debugger controls", async ({ page }) => {
    await expect(page.locator("text=Interactive Swarm Execution DAG")).toBeVisible();
    await expect(page.locator("text=Principal Architect")).toBeVisible();
    await expect(page.locator("text=Core Engineer")).toBeVisible();
    await expect(page.locator("text=Resilience Auditor")).toBeVisible();

    // Trigger step button
    const stepBtn = page.locator("button:has-text('Step (F10)')");
    await expect(stepBtn).toBeVisible();
    await stepBtn.click();
    await page.waitForTimeout(1000);
    await expect(page.locator("text=Step 2")).toBeVisible();
  });

  test("2. navigates Deterministic Time-Travel and Team Assembly tabs", async ({ page }) => {
    // Time-Travel Tab
    const timeTab = page.locator("button:has-text('Deterministic Time-Travel')");
    await expect(timeTab).toBeVisible();
    await timeTab.click();
    await expect(page.locator("text=Deterministic Execution Timeline Scrubber")).toBeVisible();
    await expect(page.locator("text=Checkpoint Fork Controller")).toBeVisible();

    // Team Assembly Tab
    const teamTab = page.locator("button:has-text('Team Auto-Assembly & Debate')");
    await expect(teamTab).toBeVisible();
    await teamTab.click();
    await expect(page.locator("text=Semantic Task Decomposition & Dynamic Agent Constellation")).toBeVisible();
    
    // Trigger Debate
    const debateBtn = page.locator("button:has-text('Initiate Consensus Debate')");
    await expect(debateBtn).toBeVisible();
    await debateBtn.click();
    await page.waitForTimeout(1500);
    await expect(page.locator("text=Consensus:")).toBeVisible();
  });
});