import { expect, test } from "@playwright/test";

import { expectNoAxeViolations } from "./axe";

test("the about page states the limits, the disclaimer and the accessibility work", async ({
  page,
}) => {
  await page.goto("/about/");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 2 })).toHaveText([
    "Before you rely on an answer",
    "Accessibility",
    "How it is built",
  ]);
  await expect(main).toContainText("No lawyer has reviewed Plumbline's answers");
  await expect(main).toContainText("Base UI Dialog");
  await expect(main.getByRole("term")).toHaveText(["/", "Enter", "Shift + Enter", "Escape"]);
  await expectNoAxeViolations(page);
});
