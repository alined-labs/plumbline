import { expect, test } from "@playwright/test";

import { expectNoAxeViolations } from "./axe";

const pages = [
  { path: "/", heading: "Ask about tenancy law", current: "Ask" },
  { path: "/check-lease/", heading: "Check a lease", current: "Check a lease" },
  { path: "/evals/", heading: "Evaluation", current: "Evaluation" },
  { path: "/about/", heading: "About Plumbline", current: "About" },
];

for (const { path, heading, current } of pages) {
  test(`${path} sits in the shell, marks its destination and is accessible`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(heading);
    await expect(page.getByRole("contentinfo")).toContainText(
      "Legal information, not legal advice.",
    );
    // On phones the destinations live in the drawer.
    if (await page.getByRole("button", { name: "Open navigation" }).isVisible()) {
      await page.getByRole("button", { name: "Open navigation" }).click();
    }
    const nav = page.getByRole("navigation", { name: "Plumbline" });
    await expect(nav.getByRole("link", { name: current, exact: true })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expectNoAxeViolations(page);
  });
}

test("the footer dates the law for each jurisdiction, in order", async ({ page }) => {
  await page.goto("/about/");
  const dates = page.getByRole("region", { name: "Statutes indexed" });
  await expect(dates.getByRole("term")).toHaveText([
    "Dubai AE-DU",
    "Spain ES",
    "Colombia CO",
    "Florida US-FL",
  ]);
});

test("the skip link moves focus to the page", async ({ page }) => {
  await page.goto("/about/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
});

test("on a phone the menu is a drawer that keeps and returns focus", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the drawer exists below 768px");
  await page.goto("/");
  const menu = page.getByRole("button", { name: "Open navigation" });
  await menu.focus();
  await page.keyboard.press("Enter");
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByRole("button", { name: "Close navigation" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(menu).toBeFocused();

  await menu.click();
  await drawer.getByRole("link", { name: "Evaluation" }).click();
  await expect(page).toHaveURL("/evals/");
  await expect(drawer).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    page.viewportSize()?.width ?? 0,
  );
});

test("between 768 and 1023px the sidebar is a rail with named icons", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "the rail is a tablet and small-laptop layout");
  await page.setViewportSize({ width: 900, height: 700 });
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Plumbline" });
  // The names stay in the accessibility tree, but the rail is only as wide as its icons.
  expect((await nav.boundingBox())?.width).toBeLessThanOrEqual(56);
  await nav.getByRole("link", { name: "Check a lease" }).hover();
  await expect(
    page.locator("[data-open]").filter({ hasText: "Check a lease" }).last(),
  ).toBeVisible();
  await expectNoAxeViolations(page);
});
