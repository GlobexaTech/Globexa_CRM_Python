import { defineConfig, devices } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const file = path.resolve(__dirname, "../evidence/fixture.json");
const origin = process.env.E2E_BASE_URL ?? (existsSync(file) ? JSON.parse(readFileSync(file, "utf8")).origin as string : "http://127.0.0.1:3254");
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  timeout: 60000,
  expect: { timeout: 15000 },
  reporter: [["list"], ["html", { outputFolder: "../evidence/playwright-report", open: "never" }], ["junit", { outputFile: "../evidence/frontend-e2e.xml" }]],
  outputDir: "../evidence/playwright-results",
  use: { baseURL: origin, screenshot: "only-on-failure", trace: "off", video: "off", actionTimeout: 15000 },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
