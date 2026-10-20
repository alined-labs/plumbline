import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { expectNoAxeViolations } from "./axe";

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
  const answer = page.getByRole("article", { name: "Answer" });
  await expect(answer).toContainText("This is a stub answer");
  const sources = answer.getByRole("list", { name: "Sources" });
  await expect(sources).toContainText("Stub Act, s. 1");
  await expect(answer).toContainText("1 source verified");
  await expectNoAxeViolations(page);

  await answer.getByRole("button", { name: "Source 1: Stub Act, s. 1" }).click();
  await expect(sources.getByRole("listitem")).toBeFocused();
});
