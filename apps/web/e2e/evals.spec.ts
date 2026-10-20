import { expect, test, type Page } from "@playwright/test";

import { expectNoAxeViolations } from "./axe";

// The evaluation page is built from the committed results files, so this build shows either
// the results or the page that waits for them. A preview built on the test fixtures
// (PLUMBLINE_EVALS_DIR=src/test/fixtures/evals pnpm build) exercises the results.

async function hasResults(page: Page) {
  await page.goto("/evals/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Evaluation");
  return (await page.getByRole("heading", { name: "Every configuration" }).count()) > 0;
}

test("the evaluation page shows its results, or says when they will appear", async ({ page }) => {
  if (!(await hasResults(page))) {
    await expect(
      page.getByText(/The results appear here after the first published run/),
    ).toBeVisible();
    await expectNoAxeViolations(page);
    return;
  }
  await expect(page.getByRole("region", { name: "Retrieval" })).toBeVisible();
  await expect(page.getByText(/95% CI /).first()).toBeVisible();
  await expect(page.getByText("Descriptive", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "How far the judge can be trusted" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /gate/ })).toHaveAttribute("href", /eval-gate/);
  // Wide tables scroll inside their own boxes; the page never scrolls sideways.
  const sideways = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(sideways).toBe(false);
  await expectNoAxeViolations(page);
});

test("the evaluation page is accessible in the dark theme", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await hasResults(page);
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  await expectNoAxeViolations(page);
});

test("a table that scrolls sideways can be reached and scrolled from the keyboard", async ({
  page,
}) => {
  test.skip(!(await hasResults(page)), "No results in this build.");
  const table = page.getByRole("region", { name: "Answers" });
  await table.focus();
  await expect(table).toBeFocused();
  const overflows = await table.evaluate((box) => box.scrollWidth > box.clientWidth);
  test.skip(!overflows, "The table fits at this width.");
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => table.evaluate((box) => box.scrollLeft)).toBeGreaterThan(0);
});
