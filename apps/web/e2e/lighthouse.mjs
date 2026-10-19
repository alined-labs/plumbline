// Runs Lighthouse CI against the static export with Playwright's Chromium, so no other
// browser has to be installed: `pnpm run lighthouse`.
import { spawnSync } from "node:child_process";

import { chromium } from "@playwright/test";

const result = spawnSync("lhci", ["autorun", "--config=lighthouserc.json"], {
  stdio: "inherit",
  env: { ...process.env, CHROME_PATH: process.env.PW_CHROMIUM_PATH || chromium.executablePath() },
  shell: false,
});
process.exit(result.status ?? 1);
