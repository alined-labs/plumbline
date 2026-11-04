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

// As the API writes them: a count it does not have is null, not missing.
const stages = [
  ["stage", { stage: "uploaded", done: null, total: null }],
  ["stage", { stage: "redacting", done: null, total: null }],
  ["stage", { stage: "reading", done: null, total: null }],
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

const ZONE = /Drop a lease here or choose a file/;

/** The start route, whatever the query (the picker sends the lease's jurisdiction and date). */
const START = (url: URL) => url.pathname === "/api/check-lease";

/** The job's two routes: the upload answers 202 with an ID, and the events route serves `run`. */
async function leaseApi(page: Page, run: string) {
  await page.route(START, (route) => route.fulfill({ status: 202, json: { id: "job-1" } }));
  await page.route("**/api/check-lease/job-1/events", (route) =>
    route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: run }),
  );
}

/** This build either takes uploads (the dropzone) or, while they are off, offers the invented
 * leases. The flows below run on whichever it shows. */
async function uploadsOn(page: Page): Promise<boolean> {
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Check a lease");
  return (await page.getByRole("button", { name: ZONE }).count()) > 0;
}

/** Where the form starts: the zone, or the picker's first lease. */
function formStart(page: Page, on: boolean) {
  return on ? page.getByRole("button", { name: ZONE }) : page.getByRole("radio").first();
}

async function chooseLease(page: Page, on: boolean) {
  if (on) {
    await page.locator('input[type="file"]').setInputFiles({
      name: "contrato.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 a lease"),
    });
  } else {
    await page.getByRole("radio", { name: /Miami/ }).check();
  }
}

async function send(page: Page, on: boolean) {
  await page.getByRole("button", { name: on ? "Check lease" : "Check this lease" }).click();
}

test("the lease page is accessible, and its zone opens the picker from the keyboard", async ({
  page,
}) => {
  await page.goto("/check-lease/");
  test.skip(!(await uploadsOn(page)), "Uploads are off in this build.");
  await expectNoAxeViolations(page);

  const zone = page.getByRole("button", { name: ZONE });
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

test("with uploads off, the page offers the invented leases and says why", async ({ page }) => {
  await page.goto("/check-lease/");
  test.skip(await uploadsOn(page), "Uploads are on in this build.");
  await expect(page.getByText("Uploads are off for now.")).toBeVisible();
  const leases = page.getByRole("group", { name: "Choose a lease to check" }).getByRole("radio");
  await expect(leases).toHaveCount(10);
  await expectNoAxeViolations(page);

  // Nothing chosen: the fix, with the focus on the list.
  await page.getByRole("button", { name: "Check this lease" }).click();
  await expect(page.getByText("Choose a lease to check", { exact: true }).last()).toBeVisible();
  await expect(leases.first()).toBeFocused();
  await expectNoAxeViolations(page);

  // From the keyboard: the arrows move between leases, as in any radio group.
  await page.keyboard.press("ArrowDown");
  await expect(leases.nth(1)).toBeChecked();
  const read = page.getByRole("link", { name: /^Read the Miami apartment lease/ });
  await expect(read).toHaveAttribute("href", "/leases/fl-lease-01.md");
  const lease = await page.request.get("/leases/fl-lease-01.md");
  expect(await lease.text()).toContain("- Lease id: fl-lease-01");
});

test("a lease goes to its findings, after the notice when it is an upload", async ({ page }) => {
  await leaseApi(page, WHOLE_RUN);
  await page.goto("/check-lease/");
  const on = await uploadsOn(page);
  const sent = page.waitForRequest((request) => START(new URL(request.url())));
  await chooseLease(page, on);
  await send(page, on);

  if (on) {
    const notice = page.getByRole("dialog", { name: "Before you upload a lease" });
    await expect(notice).toBeVisible();
    await expectNoAxeViolations(page);
    // From the keyboard: the focus is on the safe choice, Tab reaches the main one, Enter sends.
    await expect(notice.getByRole("button", { name: "Cancel" })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(notice.getByRole("button", { name: "Upload a lease" })).toBeFocused();
    await page.keyboard.press("Enter");
  } else {
    // An invented lease needs no redaction notice; it goes with its own place and date.
    const request = await sent;
    const url = new URL(request.url());
    expect(url.searchParams.get("jurisdiction")).toBe("florida");
    expect(url.searchParams.get("signed_on")).toBe("2026-08-15");
    expect(request.postData()).toContain("- Lease id: fl-lease-01");
  }

  await expect(page.getByRole("heading", { level: 2, name: "Findings" })).toBeVisible();
  await expect(page.getByText("Lease checked: 4 findings.")).toBeAttached();
  for (const group of ["Conflicts with the law", "Worth checking", "Notes", "Matches the law"]) {
    await expect(
      page.getByRole("heading", { level: 3, name: new RegExp(`^${group}`) }),
    ).toBeVisible();
  }
  await expectNoAxeViolations(page);

  // Another lease: the focus is back on the form, and no notice comes.
  await page.getByRole("button", { name: "Check another lease" }).click();
  await expect(formStart(page, on)).toBeFocused();
  await chooseLease(page, on);
  await send(page, on);
  await expect(page.getByRole("heading", { level: 2, name: "Findings" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("a check shows its steps while it runs, and a dropped stream is picked up", async ({
  page,
}) => {
  const resumed: (string | undefined)[] = [];
  await page.route(START, (route) => route.fulfill({ status: 202, json: { id: "job-1" } }));
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
  const on = await uploadsOn(page);
  await chooseLease(page, on);
  await send(page, on);

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
  await expect(formStart(page, on)).toBeFocused();
});

test("an unreadable lease says so, and offers another", async ({ page }) => {
  await page.route(START, (route) =>
    route.fulfill(problem(422, "unreadable", "The file has no text layer.")),
  );
  await page.goto("/check-lease/");
  await page.evaluate(() => window.sessionStorage.setItem("pl-lease-notice", "1"));
  const on = await uploadsOn(page);
  await chooseLease(page, on);
  await send(page, on);

  await expect(
    page.getByRole("heading", { level: 2, name: "This lease couldn't be read" }),
  ).toBeVisible();
  await expectNoAxeViolations(page);
  await page
    .getByRole("button", { name: on ? "Choose another file" : "Choose another lease" })
    .click();
  await expect(formStart(page, on)).toBeFocused();
});

test("the demo's daily limit keeps the form and the chosen lease", async ({ page }) => {
  await page.route(START, (route) =>
    route.fulfill(problem(429, "quota_reached", "Today's checks are used up.")),
  );
  await page.goto("/check-lease/");
  await page.evaluate(() => window.sessionStorage.setItem("pl-lease-notice", "1"));
  const on = await uploadsOn(page);
  await chooseLease(page, on);
  await send(page, on);

  await expect(page.getByText("Today's demo checks are used up.")).toBeVisible();
  if (on) await expect(page.getByText("contrato.pdf")).toBeVisible();
  else await expect(page.getByRole("radio", { name: /Miami/ })).toBeChecked();
  await expectNoAxeViolations(page);
});
