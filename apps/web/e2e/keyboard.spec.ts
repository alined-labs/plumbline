import { readFileSync } from "node:fs";

import { expect, test, type Locator, type Page } from "@playwright/test";

import { expectNoAxeViolations } from "./axe";

// Every flow a visitor has, by keyboard alone: no click anywhere in this file. Each step reaches
// its control the way a keyboard reader would, by Tab or the page's own shortcuts.

const stubStream = readFileSync(
  new URL("../../../packages/ts-client/fixtures/ask-stub.sse", import.meta.url),
  "utf8",
);

/** Presses Tab (or Shift+Tab) until the target has the focus; fails if it never comes. */
async function tabTo(page: Page, target: Locator, { back = false, most = 40 } = {}) {
  for (let presses = 0; presses < most; presses += 1) {
    if (await target.evaluate((element) => element === document.activeElement)) return;
    await page.keyboard.press(back ? "Shift+Tab" : "Tab");
  }
  await expect(target).toBeFocused();
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/settings/tier", (route) =>
    route.fulfill({ json: { tier: "full", updated_at: null } }),
  );
});

test("ask, read the source and copy the answer by keyboard alone", async ({
  page,
  context,
  isMobile,
}) => {
  test.skip(isMobile, "A phone has no keyboard; the drawer's own test covers its focus.");
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.route("**/api/ask", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
      body: stubStream,
    }),
  );
  await page.goto("/");
  // "/" moves to the question from anywhere on the page.
  await page.keyboard.press("/");
  const question = page.getByLabel("Your question");
  await expect(question).toBeFocused();
  await page.keyboard.type("Can my landlord keep my deposit?");
  await page.keyboard.press("Enter");

  const answer = page.getByRole("article", { name: "Answer" });
  await expect(answer.getByRole("button", { name: "Copy answer" })).toBeVisible();
  // The answer sits above the composer: back up into it to its first citation marker.
  const marker = answer.getByRole("button", { name: "Source 1: Stub Act, s. 1", exact: true });
  await tabTo(page, marker, { back: true });
  await page.keyboard.press("Enter");
  const panel = page.getByRole("dialog", { name: "Stub Act, s. 1" });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("heading", { name: "Stub Act, s. 1" })).toBeFocused();
  await expectNoAxeViolations(page);
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(marker).toBeFocused();

  const copy = answer.getByRole("button", { name: "Copy answer" });
  await tabTo(page, copy);
  await page.keyboard.press("Enter");
  await expect(answer.getByRole("button", { name: "Answer copied" })).toBeVisible();
});

test("check an invented lease by keyboard alone", async ({ page, isMobile }) => {
  test.skip(isMobile, "A phone has no keyboard.");
  await page.route(
    (url) => url.pathname === "/api/check-lease",
    (route) => route.fulfill({ status: 202, json: { id: "job-1" } }),
  );
  await page.route("**/api/check-lease/job-1/events", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: `id: 1\nevent: stage\ndata: {"stage":"uploaded"}\n\nid: 2\nevent: done\ndata: {"findings":0,"language":"en"}\n\n`,
    }),
  );
  await page.goto("/check-lease/");
  const zone = page.getByRole("button", { name: /Drop a lease here/ });
  test.skip(
    (await zone.count()) > 0,
    "Uploads are on in this build; the zone's own test covers it.",
  );
  const first = page.getByRole("radio").first();
  await tabTo(page, first);
  // Arrows move the choice within the group, as in any radio group.
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("radio").nth(1)).toBeChecked();
  await tabTo(page, page.getByRole("button", { name: "Check this lease" }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 2, name: "Findings" })).toBeVisible();
  const again = page.getByRole("button", { name: "Check another lease" });
  await tabTo(page, again);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("radio").first()).toBeFocused();
});

test("switch the theme and move between pages by keyboard alone", async ({ page, isMobile }) => {
  test.skip(isMobile, "On a phone the sidebar is a drawer, which its own test covers.");
  await page.goto("/about/");
  const toggle = page.getByRole("switch", { name: "Dark theme" });
  await tabTo(page, toggle);
  const before = await toggle.getAttribute("aria-checked");
  await page.keyboard.press("Space");
  await expect(toggle).not.toHaveAttribute("aria-checked", before ?? "");
  const evals = page
    .getByRole("navigation", { name: "Plumbline" })
    .getByRole("link", { name: "Evaluation", exact: true });
  await tabTo(page, evals, { back: true });
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/evals/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Evaluation");
});
