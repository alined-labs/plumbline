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
  await page.getByRole("button", { name: "Send question" }).click();
}

test("the home page is accessible", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ask about tenancy law");
  await expectNoAxeViolations(page);
});

test("a question streams back a cited answer", async ({ page }) => {
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await answerWithStub(page);
  await page.goto("/");
  await ask(page, "Can my landlord keep my deposit?");
  const answer = page.getByRole("article", { name: "Answer" });
  await expect(answer).toContainText("This is a stub answer");
  const sources = answer.getByRole("list", { name: "Sources" });
  await expect(sources).toContainText("Stub Act, s. 1");
  await expect(answer).toContainText("1 source verified");
  await expectNoAxeViolations(page);

  // A marker opens its passage in the focus-trapped source panel, and Escape returns to it.
  const marker = answer.getByRole("button", { name: "Source 1: Stub Act, s. 1", exact: true });
  await marker.click();
  const panel = page.getByRole("dialog", { name: "Stub Act, s. 1" });
  await expect(panel.getByRole("heading", { name: "Stub Act, s. 1" })).toBeFocused();
  await expect(panel).toContainText("This section exists only to exercise the interface.");
  await expectNoAxeViolations(page);
  const box = await panel.boundingBox();
  const viewport = page.viewportSize();
  if (box && viewport && viewport.width < 768) {
    // On a phone the panel is a bottom sheet.
    expect(Math.round(box.y + box.height)).toBe(viewport.height);
    expect(box.width).toBe(viewport.width);
  }
  // The panel sits above its scrim, so a click inside it lands on it.
  await panel.getByRole("button", { name: "Copy reference" }).click();
  await expect(panel.getByRole("button", { name: "Reference copied" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await expect(marker).toBeFocused();

  // The stream's status parts collapse into the meta line, one click away under Trace, and
  // the finished answer is announced once.
  await expect(answer).toContainText(/Answered in \d+\.\d s/);
  await answer.getByRole("button", { name: "Trace" }).click();
  await expect(answer.getByRole("list", { name: "What Plumbline is doing" })).toContainText(
    "Reading your question",
  );
  await expect(page.locator("[aria-live=polite]").filter({ hasText: "Answer:" })).toContainText(
    "This is a stub answer from the Plumbline seed. Retrieval",
  );

  // Copying keeps the evidence and the framing with the words.
  await answer.getByRole("button", { name: "Copy answer" }).click();
  await expect(answer.getByRole("button", { name: "Answer copied" })).toBeVisible();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain("Sources\n[1] Stub Act, s. 1");
  expect(copied).toContain("Legal information, not legal advice.");
});

test("a reader says why an answer did not help", async ({ page }) => {
  await answerWithStub(page);
  const sent: unknown[] = [];
  await page.route("**/api/feedback", async (route) => {
    sent.push(route.request().postDataJSON());
    await route.fulfill({ status: 204 });
  });
  await page.goto("/");
  await ask(page, "Can my landlord keep my deposit?");
  const answer = page.getByRole("article", { name: "Answer" });
  await answer.getByRole("button", { name: "Not helpful" }).click();
  const panel = answer.getByRole("group", { name: "What went wrong?" });
  await expect(panel.getByRole("button", { name: "Wrong citation" })).toBeFocused();
  await expectNoAxeViolations(page);

  await panel.getByRole("button", { name: "Wrong citation" }).click();
  await panel.getByLabel("Note").fill("The quote is from another section.");
  await panel.getByRole("button", { name: "Send" }).click();
  await expect(answer.getByText("Thanks, that helps.")).toBeVisible();
  await expect(panel).toHaveCount(0);
  expect(sent).toEqual([
    {
      request_id: "req_fixture",
      helpful: false,
      reasons: ["wrong_citation"],
      note: "The quote is from another section.",
    },
  ]);
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

test("the jurisdiction filter and as-of date travel in the request body", async ({ page }) => {
  let body: { as_of?: unknown; jurisdictions?: unknown; messages?: unknown[] } = {};
  await page.route("**/api/ask", (route) => {
    body = route.request().postDataJSON() as typeof body;
    return route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
      body: stubStream,
    });
  });
  await page.goto("/");
  await page.getByRole("combobox", { name: "Jurisdictions" }).click();
  await page.getByRole("option", { name: /Spain/ }).click();
  await page.keyboard.press("Escape");
  await page.getByLabel("Law as of").fill("2024-03-01");
  await page.getByLabel("Your question").fill("How long can a lease in Madrid last?");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("article", { name: "Answer" })).toContainText("stub answer");
  expect(body.jurisdictions).toEqual(["spain"]);
  expect(body.as_of).toBe("2024-03-01");
  expect(body.messages).toHaveLength(1);
  await expect(page.getByLabel("Your question")).toHaveValue("");
  await expectNoAxeViolations(page);
});

test("an example question asks in its own jurisdiction", async ({ page }) => {
  let body: { jurisdictions?: unknown } = {};
  await page.route("**/api/ask", (route) => {
    body = route.request().postDataJSON() as typeof body;
    return route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
      body: stubStream,
    });
  });
  await page.goto("/");
  const examples = page.getByRole("list", { name: "Example questions" });
  await expect(examples.getByRole("button")).toHaveCount(4);
  await expectNoAxeViolations(page);
  await examples.getByRole("button", { name: /CO How much can my landlord in Bogotá/ }).click();
  await expect(page.getByRole("article", { name: "Answer" })).toContainText("stub answer");
  expect(body.jurisdictions).toEqual(["colombia"]);
  await expect(examples).toHaveCount(0);
});

test("a failed answer says so and Try again asks it again", async ({ page }) => {
  const failed = [
    'data: {"type": "start", "messageId": "msg_failed"}',
    'data: {"type": "start-step"}',
    'data: {"type": "data-status", "data": {"stage": "retrieving", "detail": null}, "transient": true}',
    'data: {"type": "error", "errorText": "Something went wrong while answering."}',
    'data: {"type": "finish-step"}',
    'data: {"type": "finish", "finishReason": "error"}',
    "data: [DONE]",
  ].join("\n\n");
  let calls = 0;
  await page.route("**/api/ask", (route) => {
    calls += 1;
    return route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
      body: calls === 1 ? `${failed}\n\n` : stubStream,
    });
  });
  await page.goto("/");
  await ask(page, "Can my landlord keep my deposit?");
  const alert = page
    .getByRole("alert")
    .filter({ hasText: "Plumbline couldn't finish this answer." });
  await expect(alert).toBeVisible();
  await expectNoAxeViolations(page);
  await alert.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("article", { name: "Answer" })).toContainText("stub answer");
  await expect(alert).toHaveCount(0);
  expect(calls).toBe(2);
});

test("over the demo quota, the composer waits for the reset", async ({ page }) => {
  await page.route("**/api/ask", (route) =>
    route.fulfill({ status: 429, contentType: "application/json", body: '{"detail":"quota"}' }),
  );
  await page.goto("/");
  await ask(page, "Can my landlord keep my deposit?");
  await expect(
    page.getByRole("alert").filter({ hasText: "Today's demo questions are used up." }),
  ).toContainText(/They reset at 00:00 UTC, in \d+ (h|min)/);
  await expect(page.getByLabel("Your question")).toBeDisabled();
  await expect(
    page.getByRole("status").filter({ hasText: "Demo questions reset at 00:00 UTC" }),
  ).toBeVisible();
  await expectNoAxeViolations(page);
});

test("on a desktop the source panel sits beside the conversation and resizes from the keyboard", async ({
  page,
}, info) => {
  test.skip(info.project.name !== "desktop", "the panel is a third pane from 1024px");
  await answerWithStub(page);
  await page.goto("/");
  await ask(page, "Can my landlord keep my deposit?");
  const marker = page.getByRole("button", { name: "Source 1: Stub Act, s. 1", exact: true });
  await marker.click();
  const panel = page.getByRole("dialog", { name: "Stub Act, s. 1" });
  await expect(panel.getByRole("heading", { name: "Stub Act, s. 1" })).toBeFocused();

  // Beside the page, not over it: the conversation narrows to make room, and nothing dims.
  const viewport = page.viewportSize();
  const box = await panel.boundingBox();
  const main = await page.locator("main").boundingBox();
  expect(box && viewport && Math.round(box.x + box.width)).toBe(viewport?.width);
  expect(box && main && main.x + main.width).toBeLessThanOrEqual(box?.x ?? 0);
  await expect(page.locator("[class*=bg-overlay]")).toBeHidden();

  // Its edge is a window splitter within the panel-width tokens.
  const splitter = panel.getByRole("separator", { name: "Resize source panel" });
  await expect(splitter).toHaveAttribute("aria-valuemin", "360");
  await expect(splitter).toHaveAttribute("aria-valuemax", "640");
  await splitter.focus();
  const start = Number(await splitter.getAttribute("aria-valuenow"));
  await page.keyboard.press("ArrowLeft");
  await expect(splitter).toHaveAttribute("aria-valuenow", String(start + 16));
  await page.keyboard.press("End");
  await expect(splitter).toHaveAttribute("aria-valuenow", "640");
  expect((await panel.boundingBox())?.width).toBe(640);
  await page.keyboard.press("Home");
  await expect(splitter).toHaveAttribute("aria-valuenow", "360");
  await expectNoAxeViolations(page);

  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await expect(marker).toBeFocused();
});

test("the sidebar folds to its rail while the panel is open between 1024 and 1279px", async ({
  page,
}, info) => {
  test.skip(info.project.name !== "desktop", "the panel is a third pane from 1024px");
  await page.setViewportSize({ width: 1100, height: 760 });
  await answerWithStub(page);
  await page.goto("/");
  // The sidebar's box, which holds the nav inside its padding and edge. While the panel is open
  // the rest of the page is hidden from the accessibility tree, so this is found by CSS.
  const sidebar = page.locator('nav[aria-label="Plumbline"]').locator("..");
  expect((await sidebar.boundingBox())?.width).toBe(248);
  await ask(page, "Can my landlord keep my deposit?");
  await page.getByRole("button", { name: "Source 1: Stub Act, s. 1", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect.poll(async () => (await sidebar.boundingBox())?.width).toBe(56);
  await page.keyboard.press("Escape");
  await expect.poll(async () => (await sidebar.boundingBox())?.width).toBe(248);
});
