// Runs Lighthouse CI against the static export with Playwright's Chromium, so no other
// browser has to be installed: `pnpm run lighthouse`. Two passes over every page:
//   lighthouserc.json         the desktop preset; all four categories must stay at or above 90.
//   lighthouserc.mobile.json  Lighthouse's default phone emulation (4x CPU, a slow connection),
//                             what a reviewer gets from DevTools. Accessibility, best practices
//                             and SEO must stay at or above 90; performance is reported as a
//                             warning, because single runs spread by about five points around
//                             the chat page's median of 91 (docs/notes/mobile-performance.md).
import { spawnSync } from "node:child_process";

import { chromium } from "@playwright/test";

const env = {
  ...process.env,
  CHROME_PATH: process.env.PW_CHROMIUM_PATH || chromium.executablePath(),
};

let status = 0;
for (const config of ["lighthouserc.json", "lighthouserc.mobile.json"]) {
  const result = spawnSync("lhci", ["autorun", `--config=${config}`], {
    stdio: "inherit",
    env,
    shell: false,
  });
  status ||= result.status ?? 1;
}
process.exit(status);
