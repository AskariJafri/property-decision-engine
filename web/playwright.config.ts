import { defineConfig, devices } from "@playwright/test";

/**
 * E2E against both servers running for real.
 *
 * The suite exists because of what it already caught: the API had no CORS
 * middleware, so every browser request died at the preflight while every
 * server-side test passed. Some bugs are only visible from a browser.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: process.env.WEB_BASE ?? "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
