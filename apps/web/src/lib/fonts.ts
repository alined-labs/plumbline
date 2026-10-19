import localFont from "next/font/local";

// The three alined families, self-hosted and subset to Latin (Spanish included). Each one sets
// a --pl-face-* variable that tokens.css reads, so put all three classes on <html>:
//   <html lang="en" className={fontVariables}>

/** Atkinson Hyperlegible Next: the interface and Plumbline's own words. */
const atkinsonNext = localFont({
  src: [
    {
      path: "../fonts/AtkinsonHyperlegibleNext-Variable.woff2",
      weight: "200 800",
      style: "normal",
    },
    {
      path: "../fonts/AtkinsonHyperlegibleNext-Italic-Variable.woff2",
      weight: "200 800",
      style: "italic",
    },
  ],
  variable: "--pl-face-sans",
  display: "swap",
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

export const fontVariables = [atkinsonNext, sourceSerif, atkinsonMono]
  .map((font) => font.variable)
  .join(" ");
