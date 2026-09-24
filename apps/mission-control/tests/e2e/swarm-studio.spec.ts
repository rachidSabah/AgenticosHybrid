import { test, expect } from "@playwright/test";

// Updated for the forensic remediation: the Swarm Studio DAG no longer
// renders fabricated demo agents ("Principal Architect" / tokens / memory),
// debate results are never invented, and step status follows the backend.
test.describe("Swarm Studio & Step-Debugger E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const navBtn = page.locator("button:has-text('Swarm Studio')").first();
    await navBtn.scrollIntoViewIfNeeded();
    await navBtn.click({ force: true });
    await page.waitForSelector("text=Interactive Swarm Execution DAG", { timeout: 15000 });
  });

  test("1. DAG shows honest empty state and step controls work", async ({ page }) => {
    await expect(page.locator("text=Interactive Swarm Execution DAG")).toBeVisible();
    // Fabricated demo DAG agents were removed — the DAG must show the
    // honest empty state until the backend reports real swarm agents.
    await expect(page.locator("text=No DAG nodes reported")).toBeVisible();
    await expect(page.locator("text=Principal Architect")).toHaveCount(0);
    await expect(page.locator("text=Resilience Auditor")).toHaveCount(0);

    // Trigger step button — status derives from the backend response only.
    const stepBtn = page.locator("button:has-text('Step (F10)')");
    await expect(stepBtn).toBeVisible();
    await stepBtn.click();
    await page.waitForTimeout(1000);
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

    // Trigger Debate — the client must NOT fabricate a 96% approval result;
    // with no real consensus engine it reports the honest empty state.
    const debateBtn = page.locator("button:has-text('Initiate Consensus Debate')");
    await expect(debateBtn).toBeVisible();
    await debateBtn.click();
    await page.waitForTimeout(1500);
    await expect(page.locator("text=No consensus rounds recorded")).toBeVisible();
  });
});
