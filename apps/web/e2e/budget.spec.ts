import { brotliCompressSync, constants } from "node:zlib";

import { expect, test } from "@playwright/test";

// What each page costs before anyone touches it: the JavaScript it loads on its own, brotli
// compressed as Cloudflare Pages serves it. The size-limit budget counts every chunk the export
// ships, lazy ones too; this one holds what a first visit pays, which is what the mobile score
// and a reader on a slow connection feel (docs/notes/mobile-performance.md).
// Measured on 2026-10-20, with the chat engine loaded on first use, plus about 5%: 223.5,
// 246.1, 191.8 and 191.8 kB.
const BUDGETS_KB: Record<string, number> = {
  "/": 235,
  "/check-lease/": 258,
  "/evals/": 202,
  "/about/": 202,
};

function brotliKb(body: Buffer): number {
  return (
    brotliCompressSync(body, { params: { [constants.BROTLI_PARAM_QUALITY]: 11 } }).length / 1000
  );
}

for (const [path, budget] of Object.entries(BUDGETS_KB)) {
  test(`${path} loads at most ${budget} kB of JavaScript before any interaction`, async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "The same scripts load on a phone.");
    // Scripts that arrive before the load event: the page's own. After it, the sidebar's links
    // prefetch the other pages at low priority, which a first visit does not wait for.
    const sizes: Promise<number>[] = [];
    let loaded = false;
    page.on("load", () => {
      loaded = true;
    });
    page.on("response", (response) => {
      if (!loaded && response.request().resourceType() === "script" && response.ok()) {
        sizes.push(response.body().then(brotliKb));
      }
    });
    await page.goto(path, { waitUntil: "load" });
    const total = (await Promise.all(sizes)).reduce((sum, size) => sum + size, 0);
    test
      .info()
      .annotations.push({ type: "first-load", description: `${path} ${total.toFixed(1)} kB` });
    console.log(`first-load ${path} ${total.toFixed(1)} kB over ${sizes.length} scripts`);
    expect(total).toBeLessThanOrEqual(budget);
  });
}
