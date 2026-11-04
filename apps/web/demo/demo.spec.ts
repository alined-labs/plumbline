import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

// The demo's storyline (plan, Phase 7): a question answered with its citation, the article in
// the source panel, a question Plumbline declines, a lease with a flagged clause, the evaluation
// page and what an answer cost. Captions say what the viewer is looking at; pauses are reading
// time. Rehearsed on stubs; with DEMO_URL set it runs against the live site, unchanged.

const live = Boolean(process.env.DEMO_URL);
const QUESTION = "How long does my landlord in Florida have to return my security deposit?";
const DECLINED = "How do I evict a commercial tenant in Texas?";

/** A caption in the lower third, in the theme's inverse colours; null removes it. */
async function caption(page: Page, text: string | null, readMs = 3_500) {
  await page.evaluate((words) => {
    document.getElementById("demo-caption")?.remove();
    if (!words) return;
    const box = document.createElement("div");
    box.id = "demo-caption";
    box.setAttribute("aria-hidden", "true");
    box.textContent = words;
    Object.assign(box.style, {
      position: "fixed",
      left: "50%",
      bottom: "40px",
      transform: "translateX(-50%)",
      maxWidth: "80%",
      padding: "10px 18px",
      borderRadius: "var(--pl-radius-lg)",
      background: "var(--pl-color-inverse)",
      color: "var(--pl-color-fg-inverse)",
      font: "500 20px/28px var(--pl-font-sans), sans-serif",
      zIndex: "2147483647",
      boxShadow: "var(--pl-shadow-3)",
    });
    document.body.append(box);
  }, text);
  if (text) await page.waitForTimeout(readMs);
}

async function typeSlowly(page: Page, text: string) {
  await page.getByLabel("Your question").pressSequentially(text, { delay: 35 });
}

/** On a rehearsal, the API's recorded answers stand in for the live one. */
async function stubs(page: Page) {
  const stream = readFileSync(
    new URL("../../../packages/ts-client/fixtures/ask-stub.sse", import.meta.url),
    "utf8",
  );
  // The same stream with its answer marked abstained and its citations taken out, as the API
  // sends a question outside the law it holds.
  const declined = `${stream
    .split("\n\n")
    .filter((block) => block.startsWith("data: "))
    .flatMap((block) => {
      if (block === "data: [DONE]") return [block];
      const part = JSON.parse(block.slice("data: ".length)) as { type: string; data?: object };
      if (part.type === "data-citation") return [];
      if (part.type === "data-answer") {
        part.data = {
          ...part.data,
          status: "abstained",
          jurisdictions: [],
          abstain_reason:
            "Plumbline holds residential tenancy law for Dubai, Spain, Colombia and Florida only.",
        };
      }
      return [`data: ${JSON.stringify(part)}`];
    })
    .join("\n\n")}\n\n`;
  let asked = 0;
  await page.route("**/api/settings/tier", (route) =>
    route.fulfill({ json: { tier: "full", updated_at: null } }),
  );
  await page.route("**/api/usage", (route) =>
    route.fulfill({ json: { used: 3, limit: 20, resets_at: "2026-10-23T00:00:00Z" } }),
  );
  await page.route("**/api/ask", (route) => {
    asked += 1;
    return route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
      body: asked === 1 ? stream : declined,
    });
  });
  await page.route(
    (url) => url.pathname === "/api/check-lease",
    (route) => route.fulfill({ status: 202, json: { id: "demo-job" } }),
  );
  const finding = {
    n: 1,
    clause_number: "7",
    clause_text:
      "The Landlord shall return the deposit within 60 days, without notice of any claim.",
    clause_language: "en",
    severity: "conflict",
    title: "The deposit's deadline is longer than the law allows",
    why: "Without a claim on the deposit, the landlord has 15 days to return it.",
    citations: [
      {
        n: 1,
        chunk_id: "fl-83-49",
        ref: {
          jurisdiction: "florida",
          law: "fl-stat-83",
          article: "83.49",
          paragraph: "3(a)",
          edition: "2026",
        },
        label: "Fla. Stat. § 83.49(3)(a)",
        quote: "the landlord shall have 15 days to return the security deposit",
        gloss: null,
        language: "en",
        verified: true,
        page: null,
      },
    ],
    confidence: 0.9,
  };
  const events = [
    ["stage", { stage: "uploaded" }],
    ["stage", { stage: "redacting" }],
    ["stage", { stage: "reading" }],
    ["stage", { stage: "checking", done: 0, total: 1 }],
    ["finding", finding],
    ["stage", { stage: "checking", done: 1, total: 1 }],
    ["done", { findings: 1, language: "en" }],
  ]
    .map(
      ([event, data], index) =>
        `id: ${index + 1}\nevent: ${String(event)}\ndata: ${JSON.stringify(data)}\n\n`,
    )
    .join("");
  await page.route("**/api/check-lease/demo-job/events", (route) =>
    route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: events }),
  );
}

test("the Plumbline demo", async ({ page }) => {
  if (!live) await stubs(page);

  await page.goto("/");
  await caption(
    page,
    "Plumbline answers tenancy questions from the statutes of four jurisdictions.",
  );
  await caption(page, "Every answer cites the article it relies on, or declines.");
  await caption(page, null);

  await page.keyboard.press("/");
  await typeSlowly(page, QUESTION);
  await page.keyboard.press("Enter");
  await caption(
    page,
    "It searches the law, writes an answer, and checks every quote against the statute.",
    4_000,
  );
  const answer = page.getByRole("article", { name: "Answer" }).last();
  await expect(answer.getByRole("button", { name: "Copy answer" })).toBeVisible({
    timeout: 90_000,
  });
  await caption(page, "Each claim carries a citation marker; the quoted passage is verified.");

  await answer
    .getByRole("button", { name: /^Source 1: / })
    .first()
    .click();
  await caption(
    page,
    "The source panel shows the article itself, with the cited words marked.",
    5_000,
  );
  await page.getByRole("tab", { name: /Trace/ }).click();
  await caption(
    page,
    "The trace shows where the time went, which model answered, and what it cost.",
    5_000,
  );
  await page.keyboard.press("Escape");
  await caption(page, null);

  await typeSlowly(page, DECLINED);
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("region", { name: "I couldn't find a statute that answers this." }),
  ).toBeVisible({ timeout: 90_000 });
  await caption(
    page,
    "When the law it holds does not answer the question, it says so instead of guessing.",
  );
  await caption(page, null);

  await page
    .getByRole("navigation", { name: "Plumbline" })
    .getByRole("link", { name: "Check a lease" })
    .click();
  await caption(
    page,
    "The lease checker reads a lease clause by clause against the same statutes.",
  );
  await page.getByRole("radio", { name: /Miami apartment/ }).check();
  await page.getByRole("button", { name: "Check this lease" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Findings" })).toBeVisible({
    timeout: 120_000,
  });
  await caption(
    page,
    "Each finding quotes the clause and names the article it conflicts with.",
    5_000,
  );
  await caption(page, null);

  await page
    .getByRole("navigation", { name: "Plumbline" })
    .getByRole("link", { name: "Evaluation" })
    .click();
  await caption(page, "Every number comes from a public benchmark, with its 95% interval.", 4_500);
  await page.mouse.wheel(0, 900);
  await caption(
    page,
    "The judge's own accuracy is measured, and a gate blocks any change that makes answers worse.",
    5_000,
  );
  await caption(
    page,
    "Plumbline: legal information, with its sources, and the evidence behind every claim.",
    4_500,
  );
  await caption(page, null);
});
