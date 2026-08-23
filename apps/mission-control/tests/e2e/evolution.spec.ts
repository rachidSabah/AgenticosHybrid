import { test, expect } from "@playwright/test";

test.describe("Evolution Autonomous Self-Improvement E2E Suite", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    
    // Direct navigation via command palette
    await page.keyboard.press("Control+k");
    const palette = page.locator("[placeholder*='Search views']");
    if (await palette.isVisible({ timeout: 3000 }).catch(() => false)) {
      await palette.fill("Evolution");
      await page.keyboard.press("Enter");
    } else {
      const btn = page.locator("button:has-text('Evolution')").first();
      if (await btn.isVisible()) await btn.click({ force: true });
    }
    await page.waitForSelector("text=System Readiness", { timeout: 15000 });
  });

  test("1. validates Evolution Overview tab, readiness score, and actions", async ({ page }) => {
    await expect(page.getByText("Proposals", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "System Readiness" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Evolution Actions" })).toBeVisible();
    await expect(page.getByText("Readiness Score", { exact: true })).toBeVisible();

    // Trigger Analyze button inside Evolution Actions panel
    const analyzeCard = page.locator("div.rounded-xl", { hasText: "Analyze" }).first();
    const runBtn = analyzeCard.locator("button:has-text('Run')");
    await expect(runBtn).toBeVisible();
    await runBtn.click();
    await page.waitForTimeout(2000);
    await expect(analyzeCard).toContainText("Generated:");
  });

  test("2. navigates all Evolution sub-tabs and controls", async ({ page }) => {
    // 1. Improvement Queue tab
    const queueTab = page.locator("button:has-text('Improvement Queue')");
    await expect(queueTab).toBeVisible();
    await queueTab.click();
    await expect(page.getByRole("heading", { name: "Improvement Queue" })).toBeVisible();

    // 2. Safety Status tab
    const safetyTab = page.locator("button:has-text('Safety Status')");
    await expect(safetyTab).toBeVisible();
    await safetyTab.click();
    await expect(page.getByRole("heading", { name: "Safety Validation History" })).toBeVisible();

    // 3. Scheduler tab
    const schedulerTab = page.locator("button:has-text('Scheduler')");
    await expect(schedulerTab).toBeVisible();
    await schedulerTab.click();
    await expect(page.getByRole("heading", { name: "Execution Queue" })).toBeVisible();

    // 4. Generated Plans tab
    const plansTab = page.locator("button:has-text('Generated Plans')");
    await expect(plansTab).toBeVisible();
    await plansTab.click();
    await expect(page.getByRole("heading", { name: "Generation Plans" })).toBeVisible();

    // 5. Knowledge tab
    const knowledgeTab = page.locator("button:has-text('Knowledge')");
    await expect(knowledgeTab).toBeVisible();
    await knowledgeTab.click();
    await expect(page.getByRole("heading", { name: "Knowledge Syntheses" })).toBeVisible();
    await expect(page.locator("button:has-text('Synthesize Knowledge')")).toBeVisible();
  });
});