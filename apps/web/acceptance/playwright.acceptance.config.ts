import { defineConfig, devices } from "@playwright/test";

// The acceptance run, apart from the gate: `pnpm exec playwright test -c acceptance/playwright.acceptance.config.ts`.
// Screenshot baselines of every page in both themes on a desktop and a phone, taken from this
// build's export; with ACCEPT_URL set, the same baselines against the live site plus the demo's
// path through the real API (acceptance/README.md).
process.env.ACCEPT_PORT ??= String(33_000 + (process.pid % 1_000));
const port = Number(process.env.ACCEPT_PORT);
const live = Boolean(process.env.ACCEPT_URL);

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  timeout: 3 * 60_000,
  workers: 2,
  reporter: "list",
  // Git ignores test-results/; the baselines themselves live beside this file.
  outputDir: "../test-results/acceptance",
  // The export and the live site differ by design (the live sidebar has the usage meter, the live
  // /evals its results), so each keeps its own baselines.
  snapshotPathTemplate: `{testDir}/baselines/${live ? "live" : "export"}/{projectName}/{arg}{ext}`,
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: "disabled", caret: "hide" } },
  use: {
    baseURL: process.env.ACCEPT_URL ?? `http://127.0.0.1:${port}`,
    launchOptions: { executablePath: process.env.PW_CHROMIUM_PATH || undefined },
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: live
    ? undefined
    : {
        command: `node e2e/serve.mjs out ${port}`,
        cwd: "..",
        url: `http://127.0.0.1:${port}`,
        reuseExistingServer: false,
      },
});
