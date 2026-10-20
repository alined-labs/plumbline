import { chooseTheme, chosenTheme, THEME_KEY, THEME_SCRIPT } from "./theme";

afterEach(() => {
  delete document.documentElement.dataset.theme;
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("theme", () => {
  it("follows the system until the reader chooses, then keeps the choice", () => {
    expect(chosenTheme()).toBeNull();
    chooseTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(chosenTheme()).toBe("dark");
  });

  it("still switches when storage is refused", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    chooseTheme("light");
    expect(chosenTheme()).toBe("light");
  });

  it("applies a stored choice from the head script, and ignores anything else", () => {
    localStorage.setItem(THEME_KEY, "dark");
    new Function(THEME_SCRIPT)();
    expect(chosenTheme()).toBe("dark");

    delete document.documentElement.dataset.theme;
    localStorage.setItem(THEME_KEY, "purple");
    new Function(THEME_SCRIPT)();
    expect(chosenTheme()).toBeNull();
  });
});
