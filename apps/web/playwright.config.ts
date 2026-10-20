import { defineConfig, devices } from "@playwright/test";

// Each run serves its own export on a port of its own. A fixed port let one run reuse another's
// server (a leftover of mine, or the hub's check beside a lane's), and so test a different
// build from the one it had just made. The first process to load this file picks the port and
// puts it in the environment, which the workers it starts inherit; set E2E_PORT to pin it.
// 20000 to 31999 is below Linux's ephemeral ports and clear of the ports Chromium refuses.
process.env.E2E_PORT ??= String(20_000 + (process.pid % 12_000));
const port = Number(process.env.E2E_PORT);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    // A machine whose Chromium is not Playwright's own can point at it.
    launchOptions: { executablePath: process.env.PW_CHROMIUM_PATH || undefined },
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: `node e2e/serve.mjs out ${port}`,
    url: `http://127.0.0.1:${port}`,
    // Never reuse: a server already on this port serves some other build.
    reuseExistingServer: false,
  },
});
