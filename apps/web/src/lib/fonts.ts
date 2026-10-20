import localFont from "next/font/local";

// The alined families, self-hosted and subset to Latin (Spanish included). Each one sets a
// --pl-face-* variable that tokens.css (or globals.css, for the italic) reads, so put every
// class on <html>:
//   <html lang="en" className={fontVariables}>

/** Atkinson Hyperlegible Next: the interface and Plumbline's own words. Upright only: the one
 * face the first paint needs, so it is the one that is preloaded. */
const atkinsonNext = localFont({
  src: "../fonts/AtkinsonHyperlegibleNext-Variable.woff2",
  weight: "200 800",
  style: "normal",
  variable: "--pl-face-sans",
  display: "swap",
});

/** The same family's italic, in a face of its own so it is fetched only when emphasised text
 * is on the page (globals.css points em, i and cite at it), not preloaded with every page. */
const atkinsonNextItalic = localFont({
  src: "../fonts/AtkinsonHyperlegibleNext-Italic-Variable.woff2",
  weight: "200 800",
  style: "italic",
  variable: "--pl-face-sans-italic",
  display: "swap",
  preload: false,
});

/** Source Serif 4 at its text optical size: the statutes' own words, nothing else. */
const sourceSerif = localFont({
  src: [
    { path: "../fonts/SourceSerif4-Variable.woff2", weight: "300 700", style: "normal" },
    { path: "../fonts/SourceSerif4-Italic-Variable.woff2", weight: "300 700", style: "italic" },
  ],
  variable: "--pl-face-serif",
  display: "swap",
  adjustFontFallback: "Times New Roman",
  preload: false,
});

/** Atkinson Hyperlegible Mono: jurisdiction codes, IDs, trace data and eyebrows. */
const atkinsonMono = localFont({
  src: "../fonts/AtkinsonHyperlegibleMono-Variable.woff2",
  weight: "200 800",
  variable: "--pl-face-mono",
  display: "swap",
  adjustFontFallback: false,
  preload: false,
});

export const fontVariables = [atkinsonNext, atkinsonNextItalic, sourceSerif, atkinsonMono]
  .map((font) => font.variable)
  .join(" ");
