// The theme switch. Without a choice the page follows prefers-color-scheme; a choice sets
// data-theme on <html> (tokens.css reads it) and is kept in localStorage. Storage can be
// refused (private windows, blocked cookies), so every access sits in try and catch.

export type Theme = "light" | "dark";

export const THEME_KEY = "plumbline-theme";
const CHANGE = "plumbline-theme-change";

/** Runs in <head> before the first paint, so a stored choice never flashes the other theme. */
export const THEME_SCRIPT = `try{var t=localStorage.getItem("${THEME_KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

/** The theme the reader chose, as applied to the page, or null to follow the system. */
export function chosenTheme(): Theme | null {
  const theme = document.documentElement.dataset.theme;
  return theme === "light" || theme === "dark" ? theme : null;
}

export function chooseTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // The choice still holds for this page; it is not remembered.
  }
  window.dispatchEvent(new Event(CHANGE));
}

export function onThemeChange(callback: () => void): () => void {
  window.addEventListener(CHANGE, callback);
  return () => window.removeEventListener(CHANGE, callback);
}
