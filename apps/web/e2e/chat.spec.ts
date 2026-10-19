import { readFileSync } from "node:fs";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// The exact bytes the API's stub streams (written by `make openapi`), so this test breaks
// when the stream contract changes on either side.
const stubStream = readFileSync(
  new URL("../../../packages/ts-client/fixtures/ask-stub.sse", import.meta.url),
  "utf8",
);

async function answerWithStub(page: Page) {
  await page.route("**/api/ask", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
      body: stubStream,
    }),
  );
}

async function expectNoAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations).toEqual([]);
}

test("the home page is accessible", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ask about tenancy law");
  await expectNoAxeViolations(page);
});

test("a question streams back a cited answer", async ({ page }) => {
  await answerWithStub(page);
  await page.goto("/");
  await page.getByLabel("Your question").fill("Can my landlord keep my deposit?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByText(/This is a stub answer/)).toBeVisible();
  await expect(page.getByRole("list", { name: "Citations" })).toContainText("Stub Act, s. 1");
  await expectNoAxeViolations(page);
});
