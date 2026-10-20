import "@testing-library/jest-dom/vitest";

// jsdom has no matchMedia: every query reports false (a narrow, light-themed window) unless a
// test overrides it.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) satisfies MediaQueryList;
}
