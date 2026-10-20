import { expect, test, type Page } from "@playwright/test";

import { expectNoAxeViolations } from "./axe";

// Findings in the shape Lane C's checker returns (leases/schema.py): one of each severity,
// all citing the invented "Stub Act" the answer stub cites, as Lane D's stand-in checker does.
const citation = {
  n: 1,
  chunk_id: "stub-act-1",
  ref: { jurisdiction: "florida", law: "stub-act", article: "1", paragraph: null, edition: "seed" },
  label: "Stub Act, s. 1",
  quote: "This section exists only to exercise the interface.",
  gloss: null,
  language: "en",
  verified: true,
  page: null,
};
const finding = (n: number, severity: string, title: string) => ({
  n,
  clause_number: String(n),
  clause_text: `Stub clause ${n}, which stands in for a clause of your lease.`,
  clause_language: "en",
  severity,
  title,
  why: "This is a stub finding from the Plumbline seed, so nothing here is legal information.",
  citations: [citation],
  confidence: 0.5,
});

/** The job's event stream as the API writes it: an id on every event. */
function events(...list: [string, object][]): string {
  return list
    .map(
      ([event, data], index) =>
        `id: ${index + 1}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
    )
    .join("");
}

const stages = [
  ["stage", { stage: "uploaded" }],
  ["stage", { stage: "redacting" }],
  ["stage", { stage: "reading" }],
  ["stage", { stage: "checking", done: 0, total: 4 }],
] satisfies [string, object][];
const checked = (n: number): [string, object] => [
  "stage",
  { stage: "checking", done: n, total: 4 },
];

const WHOLE_RUN = events(
  ...stages,
  ["finding", finding(1, "conflict", "A stub clause that conflicts with the law")],
  checked(1),
  ["finding", finding(2, "check", "A stub clause worth a second look")],
  checked(2),
  ["finding", finding(3, "note", "A stub clause that leaves something out")],
  checked(3),
  ["finding", finding(4, "match", "A stub clause that follows the law")],
  checked(4),
  ["done", { findings: 4, language: "en" }],
);

const problem = (status: number, code: string, detail: string) => ({
  status,
  headers: { "content-type": "application/problem+json" },
  body: JSON.stringify({ type: "about:blank", title: detail, status, detail, code }),
});

/** The job's two routes: the upload answers 202 with an ID, and the events route serves `run`. */
async function leaseApi(page: Page, run: string) {
  await page.route("**/api/check-lease", (route) =>
    route.fulfill({ status: 202, json: { id: "job-1" } }),
  );
  await page.route("**/api/check-lease/job-1/events", (route) =>
    route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: run }),
  );
}

async function chooseLease(page: Page) {
  await page.locator('input[type="file"]').setInputFiles({
    name: "contrato.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 a lease"),
  });
}

test("the lease page is accessible, and its zone opens the picker from the keyboard", async ({
  page,
}) => {
  await page.goto("/check-lease/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Check a lease");
  await expectNoAxeViolations(page);

  const zone = page.getByRole("button", { name: /Drop a lease here or choose a file/ });
  await zone.focus();
  const chooser = page.waitForEvent("filechooser");
  await page.keyboard.press("Enter");
  await (
    await chooser
  ).setFiles({
    name: "contrato.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 a lease"),
  });
  await expect(page.getByText("contrato.pdf")).toBeVisible();
});

test("a lease goes from the notice to its findings, and the notice comes once", async ({
  page,
}) => {
  await leaseApi(page, WHOLE_RUN);
  await page.goto("/check-lease/");
  await chooseLease(page);
  await page.getByRole("button", { name: "Check lease" }).click();

  const notice = page.getByRole("dialog", { name: "Before you upload a lease" });
  await expect(notice).toBeVisible();
  await expectNoAxeViolations(page);
  // From the keyboard: the focus is on the safe choice, Tab reaches the main one, Enter sends.
  await expect(notice.getByRole("button", { name: "Cancel" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(notice.getByRole("button", { name: "Upload a lease" })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect(page.getByRole("heading", { level: 2, name: "Findings" })).toBeVisible();
  await expect(page.getByText("Lease checked: 4 findings.")).toBeAttached();
  for (const group of ["Conflicts with the law", "Worth checking", "Notes", "Matches the law"]) {
    await expect(
      page.getByRole("heading", { level: 3, name: new RegExp(`^${group}`) }),
    ).toBeVisible();
  }
  await expectNoAxeViolations(page);

  // Another lease: the focus is back on the zone, and the notice does not return.
  await page.getByRole("button", { name: "Check another lease" }).click();
  await expect(
    page.getByRole("button", { name: /Drop a lease here or choose a file/ }),
  ).toBeFocused();
  await chooseLease(page);
  await page.getByRole("button", { name: "Check lease" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Findings" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("a check shows its steps while it runs, and a dropped stream is picked up", async ({
  page,
}) => {
  const resumed: (string | undefined)[] = [];
  await page.route("**/api/check-lease", (route) =>
    route.fulfill({ status: 202, json: { id: "job-1" } }),
  );
  let calls = 0;
  await page.route("**/api/check-lease/job-1/events", async (route) => {
    resumed.push(route.request().headers()["last-event-id"]);
    calls += 1;
    if (calls === 1) {
      // Two findings, then the connection ends before the check does.
      await route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream" },
        body: events(
          ...stages,
          ["finding", finding(1, "conflict", "A stub clause that conflicts with the law")],
          checked(1),
          ["finding", finding(2, "check", "A stub clause worth a second look")],
          checked(2),
        ),
      });
    } else {
      // The picked-up stream never answers: the page stays as it is while the check runs.
      await new Promise(() => {});
    }
  });
  await page.goto("/check-lease/");
  await page.evaluate(() => window.sessionStorage.setItem("pl-lease-notice", "1"));
  await chooseLease(page);
  await page.getByRole("button", { name: "Check lease" }).click();

  await expect(page.getByRole("heading", { level: 2, name: "Checking your lease" })).toBeVisible();
  await expect(page.locator('li[aria-current="step"]')).toContainText("Checking clauses · 2 of 4");
  await expect(page.getByRole("progressbar", { name: "Checking the lease" })).toHaveAttribute(
    "aria-valuenow",
    "50",
  );
  await expect(
    page.getByRole("heading", { level: 3, name: /^Conflicts with the law/ }),
  ).toBeVisible();
  await expect.poll(() => calls).toBe(2);
  expect(resumed).toEqual([undefined, "8"]);
  await expectNoAxeViolations(page);

  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(
    page.getByRole("button", { name: /Drop a lease here or choose a file/ }),
  ).toBeFocused();
});

test("an unreadable lease says so, and offers another file", async ({ page }) => {
  await page.route("**/api/check-lease", (route) =>
    route.fulfill(problem(422, "unreadable", "The file has no text layer.")),
  );
  await page.goto("/check-lease/");
  await page.evaluate(() => window.sessionStorage.setItem("pl-lease-notice", "1"));
  await chooseLease(page);
  await page.getByRole("button", { name: "Check lease" }).click();

  await expect(
    page.getByRole("heading", { level: 2, name: "This lease couldn't be read" }),
  ).toBeVisible();
  await expect(page.getByText("The file has no selectable text.")).toBeVisible();
  await expectNoAxeViolations(page);
  await page.getByRole("button", { name: "Choose another file" }).click();
  await expect(
    page.getByRole("button", { name: /Drop a lease here or choose a file/ }),
  ).toBeFocused();
});

test("the demo's daily limit keeps the form and the chosen file", async ({ page }) => {
  await page.route("**/api/check-lease", (route) =>
    route.fulfill(problem(429, "quota_reached", "Today's checks are used up.")),
  );
  await page.goto("/check-lease/");
  await page.evaluate(() => window.sessionStorage.setItem("pl-lease-notice", "1"));
  await chooseLease(page);
  await page.getByRole("button", { name: "Check lease" }).click();

  await expect(page.getByText("Today's demo checks are used up.")).toBeVisible();
  await expect(page.getByText("contrato.pdf")).toBeVisible();
  await expectNoAxeViolations(page);
});
