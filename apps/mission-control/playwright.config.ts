import { defineConfig, devices } from "@playwright/test";

// E2E target port — defaults to 3000 (CI serves the static export there via
// `npm run start`). Override with E2E_PORT to run against another port locally
// (e.g. E2E_PORT=3100 when the dev sandbox reserves port 3000).
const PORT = process.env.E2E_PORT ?? "3000";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",
  timeout: 60000,
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "on-first-retry",
    screenshot: "on",
    video: "retain-on-failure",
    actionTimeout: 20000,
    navigationTimeout: 30000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-chrome",
      use: { ...devices["Pixel 5"] },
    },
    {
      name: "tablet-chrome",
      use: { ...devices["iPad Mini"] },
    },
  ],
  webServer: {
    command: process.env.CI
      ? "npm run start"
      : `npx serve -s out -l ${PORT}`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: true,
    timeout: 120 * 1000,
  },
});

