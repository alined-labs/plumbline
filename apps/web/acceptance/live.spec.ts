import { expect, test } from "@playwright/test";

// The demo's path through the real API, run only against a deployed site (ACCEPT_URL): an
// answer with a verified citation, its article in the panel, the visitor cookie, an invented
// lease's findings and the evaluation page. It spends two of the day's demo allowance.

test.skip(!process.env.ACCEPT_URL, "Runs only against a deployed site (ACCEPT_URL).");

test("a question is answered with a verified citation and its article", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Your question")
    .fill("How long does my landlord in Florida have to return my security deposit?");
  await page.getByRole("button", { name: "Send question" }).click();
  const answer = page.getByRole("article", { name: "Answer" }).last();
  await expect(answer.getByRole("button", { name: "Copy answer" })).toBeVisible({
    timeout: 120_000,
  });
  await expect(answer.getByText(/sources? verified/)).toBeVisible();
  await answer
    .getByRole("button", { name: /^Source 1: / })
    .first()
    .click();
  await expect(page.getByRole("dialog").locator("blockquote, [role=region]").first()).toBeVisible();
  // The API set the visitor cookie for its own host, and the site sent it back.
  const api = new URL(process.env.ACCEPT_API_URL ?? process.env.ACCEPT_URL ?? "");
  const cookies = await context.cookies(api.origin);
  expect(cookies.map((cookie) => cookie.name)).toContain("plumbline_visitor");
  await expect(page.getByRole("meter", { name: "Demo questions used" })).toBeVisible();
});

test("an invented lease is checked to its findings", async ({ page }) => {
  await page.goto("/check-lease/");
  await page.getByRole("radio", { name: /Miami apartment/ }).check();
  await page.getByRole("button", { name: "Check this lease" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Findings" })).toBeVisible({
    timeout: 180_000,
  });
  await expect(
    page.getByRole("heading", { level: 3, name: /^Conflicts with the law/ }),
  ).toBeVisible();
});

test("the evaluation page shows measured results", async ({ page }) => {
  await page.goto("/evals/");
  await expect(page.getByRole("heading", { name: "Every configuration" })).toBeVisible();
  await expect(page.getByText(/95% CI /).first()).toBeVisible();
});
