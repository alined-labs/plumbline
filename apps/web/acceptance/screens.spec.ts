import { expect, test } from "@playwright/test";

// Every page as it first appears, in both themes: a change that moves a pixel past 1% of the
// screen fails here until the baseline is updated on purpose (`--update-snapshots`). The usage
// meter's count changes through the day, so it is masked.

const PAGES = [
  { path: "/", name: "chat" },
  { path: "/check-lease/", name: "lease" },
  { path: "/evals/", name: "evals" },
  { path: "/about/", name: "about" },
];

for (const theme of ["light", "dark"] as const) {
  for (const { path, name } of PAGES) {
    test(`${name} in the ${theme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      await page.goto(path);
      await page.evaluate(async () => {
        await document.fonts.ready;
      });
      await expect(page.getByRole("heading", { level: 1 })).toBeAttached();
      await expect(page).toHaveScreenshot(`${name}-${theme}.png`, {
        mask: [page.getByRole("meter", { name: "Demo questions used" })],
      });
    });
  }
}
