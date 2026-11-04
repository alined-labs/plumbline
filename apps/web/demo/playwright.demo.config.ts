import { defineConfig, devices } from "@playwright/test";

// The screen-recorded demo, not a test: `pnpm exec playwright test -c demo/playwright.demo.config.ts`.
// It walks the visitor's path at reading pace with captions and records it as video
// (demo/README.md). Against the live site set DEMO_URL; otherwise it serves this build's export
// and answers from the API's recorded stubs, which is how the script is rehearsed.
process.env.DEMO_PORT ??= String(32_000 + (process.pid % 1_000));
const port = Number(process.env.DEMO_PORT);
const live = Boolean(process.env.DEMO_URL);

export default defineConfig({
  testDir: ".",
  testMatch: "demo.spec.ts",
  timeout: 10 * 60_000,
  workers: 1,
  reporter: "list",
  // Git ignores test-results/: the video stays out of the repository until it is published.
  outputDir: "../test-results/demo",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.DEMO_URL ?? `http://127.0.0.1:${port}`,
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 2,
    video: { mode: "on", size: { width: 1280, height: 720 } },
    colorScheme: process.env.DEMO_THEME === "dark" ? "dark" : "light",
    launchOptions: { executablePath: process.env.PW_CHROMIUM_PATH || undefined },
  },
  webServer: live
    ? undefined
    : {
        command: `node e2e/serve.mjs out ${port}`,
        cwd: "..",
        url: `http://127.0.0.1:${port}`,
        reuseExistingServer: false,
      },
});
