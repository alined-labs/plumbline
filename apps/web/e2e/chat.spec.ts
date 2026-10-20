import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { expectNoAxeViolations } from "./axe";

// The exact bytes the API's stub streams (written by `make openapi`), so this test breaks
// when the stream contract changes on either side.
const stubStream = readFileSync(
  new URL("../../../packages/ts-client/fixtures/ask-stub.sse", import.meta.url),
  "utf8",
);

/** The stub stream with its data-answer payload changed (the partial and abstained shapes),
 * optionally without its citations. */
function stubStreamWith(answer: Record<string, unknown>, { citations = true } = {}): string {
  const parts = stubStream
    .split("\n\n")
    .filter((block) => block.startsWith("data: "))
    .map((block) => {
      if (block === "data: [DONE]") return block;
      const part = JSON.parse(block.slice("data: ".length)) as { type: string; data?: object };
      if (!citations && part.type === "data-citation") return null;
      if (part.type === "data-answer") part.data = { ...part.data, ...answer };
      return `data: ${JSON.stringify(part)}`;
    })
    .filter((block) => block !== null);
  return `${parts.join("\n\n")}\n\n`;
}

async function answerWithStub(page: Page, body = stubStream) {
  await page.route("**/api/ask", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
      body,
    }),
  );
}

async function ask(page: Page, question: string) {
  await page.getByLabel("Your question").fill(question);
  await page.getByRole("button", { name: "Ask" }).click();
}

test("the home page is accessible", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ask about tenancy law");
  await expectNoAxeViolations(page);
});

test("a question streams back a cited answer", async ({ page }) => {
  await answerWithStub(page);
  await page.goto("/");
  await ask(page, "Can my landlord keep my deposit?");
  const answer = page.getByRole("article", { name: "Answer" });
  await expect(answer).toContainText("This is a stub answer");
  const sources = answer.getByRole("list", { name: "Sources" });
  await expect(sources).toContainText("Stub Act, s. 1");
  await expect(answer).toContainText("1 source verified");
  await expectNoAxeViolations(page);

  await answer.getByRole("button", { name: "Source 1: Stub Act, s. 1" }).click();
  await expect(sources.getByRole("listitem")).toBeFocused();
});

test("a partial answer names the part it leaves out", async ({ page }) => {
  await answerWithStub(page, stubStreamWith({ status: "partial", abstain_reason: null }));
  await page.goto("/");
  await ask(page, "Can my landlord in Dubai end the lease to sell, and raise the rent?");
  const answer = page.getByRole("article", { name: "Answer" });
  await expect(answer).toContainText("Partial answer");
  await expect(answer).toContainText("Not covered by the statutes I hold");
  await expect(answer.getByRole("list", { name: "Sources" })).toBeVisible();
  await expectNoAxeViolations(page);
});

test("an abstention is calm, says what was checked and shows no sources", async ({ page }) => {
  await answerWithStub(
    page,
    stubStreamWith(
      { status: "abstained", jurisdictions: [], abstain_reason: "Texas is not in the corpus." },
      { citations: false },
    ),
  );
  await page.goto("/");
  await ask(page, "Can my landlord in Austin, Texas keep my deposit?");
  const abstention = page.getByRole("region", {
    name: "I couldn't find a statute that answers this.",
  });
  await expect(abstention).toContainText("Texas is not in the corpus.");
  await expect(abstention).toContainText("What you can do");
  await expect(page.getByRole("list", { name: "Sources" })).toHaveCount(0);
  await expectNoAxeViolations(page);
});
