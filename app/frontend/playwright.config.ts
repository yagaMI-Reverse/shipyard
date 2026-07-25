import { defineConfig, devices } from "@playwright/test";

/**
 * E2E suite for DocuChat. Runs against the deployed app by default
 * (E2E_BASE_URL overrides — e.g. a local dev server). The live backend on
 * Render cold-starts, so the global setup warms it before any spec runs.
 */
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 90_000,
  expect: { timeout: 45_000 },
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://yagami-reverse.github.io/docuchat/",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    // Pixel 7 = Chromium-based mobile emulation, so the suite needs only the
    // chromium binary (WebKit isn't installed in this environment).
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
