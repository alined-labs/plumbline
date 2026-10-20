import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ThemeSwitch } from "./theme-switch";

afterEach(() => {
  delete document.documentElement.dataset.theme;
  localStorage.clear();
});

describe("ThemeSwitch", () => {
  it("shows the theme in use and switches it", async () => {
    render(<ThemeSwitch />);
    const toggle = screen.getByRole("switch", { name: "Dark theme" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await userEvent.setup().click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
