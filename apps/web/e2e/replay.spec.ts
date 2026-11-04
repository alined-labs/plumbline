import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { expectNoAxeViolations } from "./axe";

// The static tier: the API says so, or does not answer at all. The page then offers the stored
// dev answers from /replay.json, here the test fixture in the file's own shape.
const items = readFileSync(
  new URL("../src/test/fixtures/evals/replay/A2/dev.jsonl", import.meta.url),
  "utf8",
)
  .split("\n")
  .filter(Boolean)
  .map((line) => JSON.parse(line) as unknown);

async function staticTier(page: Page, how: "static" | "unreachable" = "static") {
  await page.route("**/api/settings/tier", (route) =>
    how === "static"
      ? route.fulfill({ json: { tier: "static", updated_at: null } })
      : route.abort("connectionrefused"),
  );
  await page.route("**/replay.json", (route) =>
    route.fulfill({ json: { config: "A2", config_hash: "0".repeat(64), items } }),
  );
}

test("the static tier offers the recorded answers instead of the composer", async ({ page }) => {
  const calls: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) calls.push(new URL(request.url()).pathname);
  });
  await staticTier(page);
  await page.goto("/");
  await expect(page.getByText("The live demo is paused.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recorded questions" })).toBeVisible();
  // The composer stays where it was, closed, so nothing moves when the page turns out static.
  await expect(page.getByLabel("Your question")).toBeDisabled();
  await expect(page.getByText(/choose one of the recorded questions above/)).toBeVisible();
  await expect(page.getByRole("heading", { level: 3, name: /Florida/ })).toBeVisible();
  await expectNoAxeViolations(page);

  await page.getByRole("button", { name: /deposit in Florida/ }).click();
  const answer = page.getByRole("article", { name: "Answer" });
  await expect(answer).toContainText("within 15 days");
  // A recorded answer has no request to attach a verdict to.
  await expect(answer.getByRole("button", { name: /helpful/i })).toHaveCount(0);
  await expectNoAxeViolations(page);

  await answer
    .getByRole("button", { name: "Source 1: Fla. Stat. § 83.49(3)(a)", exact: true })
    .click();
  const panel = page.getByRole("dialog", { name: "Fla. Stat. § 83.49(3)(a)" });
  await expect(panel.locator("blockquote")).toHaveText(
    "the landlord shall have 15 days to return the security deposit",
  );
  await expect(panel.getByText(/recorded demo shows the quoted passage alone/)).toBeVisible();
  await page.keyboard.press("Escape");

  // Back to the list, with the focus on the question just read.
  await page.getByRole("button", { name: "Another question" }).click();
  await expect(page.getByRole("button", { name: /deposit in Florida/ })).toBeFocused();
  // Only the tier was asked: no usage count, no article, no answer.
  expect(calls).toEqual(["/api/settings/tier"]);
});

test("a withheld passage shows as its citation alone", async ({ page }) => {
  await staticTier(page);
  await page.goto("/");
  await page.getByRole("button", { name: /cash deposit/ }).click();
  const answer = page.getByRole("article", { name: "Answer" });
  await expect(
    answer.getByText("The publisher's terms do not let us republish this passage."),
  ).toBeVisible();
  await expect(answer).not.toContainText("[Withheld");
  await expectNoAxeViolations(page);
});

test("when the API does not answer, a failed question offers the recorded answers", async ({
  page,
}) => {
  await staticTier(page, "unreachable");
  await page.route("**/api/ask", (route) => route.abort("connectionrefused"));
  await page.goto("/");
  // Live until a question shows otherwise: the page does not swap itself after drawing.
  await expect(page.getByLabel("Your question")).toBeEnabled();
  await page.getByLabel("Your question").fill("Can my landlord keep my deposit?");
  await page.getByRole("button", { name: "Send question" }).click();
  await page.getByRole("button", { name: "read the answers Plumbline recorded" }).click();
  await expect(page.getByText("The live demo is paused.")).toBeVisible();
  await page.getByRole("button", { name: /Texas/ }).click();
  await expect(page.getByRole("article", { name: "Answer" })).toContainText(
    "Plumbline holds residential tenancy law for Dubai, Spain, Colombia and Florida only.",
  );
  await expectNoAxeViolations(page);
});

test("the dark theme passes axe on the recorded list", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await staticTier(page);
  await page.goto("/");
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  await expect(page.getByRole("heading", { name: "Recorded questions" })).toBeVisible();
  await expectNoAxeViolations(page);
});

test("before any answer is recorded, nothing points at an empty list", async ({ page }) => {
  await page.route("**/api/settings/tier", (route) => route.abort("connectionrefused"));
  await page.route("**/api/ask", (route) => route.abort("connectionrefused"));
  await page.route("**/replay.json", (route) =>
    route.fulfill({ json: { config: null, config_hash: null, items: [] } }),
  );
  await page.goto("/");
  await page.getByLabel("Your question").fill("Can my landlord keep my deposit?");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.getByText("Plumbline couldn't finish this answer.")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "read the answers Plumbline recorded" }),
  ).toHaveCount(0);
});

test("a static tier with nothing recorded says it is paused, and no more", async ({ page }) => {
  await page.route("**/api/settings/tier", (route) =>
    route.fulfill({ json: { tier: "static", updated_at: null } }),
  );
  await page.route("**/replay.json", (route) =>
    route.fulfill({ json: { config: null, config_hash: null, items: [] } }),
  );
  await page.goto("/");
  await expect(page.getByText("The live demo is paused.")).toBeVisible();
  await expect(page.getByText("The live demo is paused for now.")).toBeVisible();
  await expect(page.getByText(/recorded questions above/)).toHaveCount(0);
  await expectNoAxeViolations(page);
});
