import { expect, test, type Page } from "@playwright/test";

import { expectNoAxeViolations } from "./axe";

// The evaluation page is built from the committed files under evals/, so one build shows one of
// three states: nothing yet (the page says when the results will appear); the judge's calibration
// alone (evals/calibration/agreement.json, before the first published run); or the results, with
// the calibration beside them. A preview built on the test fixtures
// (PLUMBLINE_EVALS_DIR=src/test/fixtures/evals pnpm build) exercises the last.

type State = "pending" | "calibration" | "results";

async function stateOf(page: Page): Promise<State> {
  await page.goto("/evals/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Evaluation");
  // The retrieval table is built from results files alone; the judge's section from either.
  if ((await page.getByRole("region", { name: "Retrieval" }).count()) > 0) return "results";
  const judge = page.getByRole("heading", { name: "How far the judge can be trusted" });
  return (await judge.count()) > 0 ? "calibration" : "pending";
}

async function expectNoSidewaysScroll(page: Page) {
  // Wide tables scroll inside their own boxes; the page never scrolls sideways.
  const sideways = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(sideways).toBe(false);
}

test("the evaluation page shows its results, the judge alone, or says when they will appear", async ({
  page,
}) => {
  const state = await stateOf(page);
  if (state === "pending") {
    await expect(
      page.getByText(/The results appear here after the first published run/),
    ).toBeVisible();
    await expectNoAxeViolations(page);
    return;
  }
  if (state === "calibration") {
    await expect(page.getByText(/No run is published yet/)).toBeVisible();
    await expect(page.getByRole("region", { name: "The judge's accuracy" })).toBeVisible();
    await expect(page.getByText(/appear here after the first published run/)).toBeVisible();
    await expect(page.getByRole("heading", { name: /The default configuration/ })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Latency and cost" })).toHaveCount(0);
    await expectNoSidewaysScroll(page);
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
  await expectNoSidewaysScroll(page);
  await expectNoAxeViolations(page);
});

test("the evaluation page is accessible in the dark theme", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await stateOf(page);
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  await expectNoAxeViolations(page);
});

test("a table that scrolls sideways can be reached and scrolled from the keyboard", async ({
  page,
}) => {
  test.skip((await stateOf(page)) !== "results", "No results in this build.");
  const table = page.getByRole("region", { name: "Answers" });
  await table.focus();
  await expect(table).toBeFocused();
  const overflows = await table.evaluate((box) => box.scrollWidth > box.clientWidth);
  test.skip(!overflows, "The table fits at this width.");
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => table.evaluate((box) => box.scrollLeft)).toBeGreaterThan(0);
});
