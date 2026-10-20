# Mobile performance

Lighthouse's desktop preset, which the gate enforces, scores every page 100. Its default phone emulation (4× slower CPU, a slow connection), which is what a reviewer gets from DevTools, is harder: this note records what it measured, what moved it, and what is left. Measured on 2026-10-20 on MX3 against the static export; each figure is the median of five to seven runs, because single runs spread by ±5 points.

## Where it started

| Page | Performance | Total blocking time |
| --- | ---: | ---: |
| `/` (chat) | 81 | 715 ms |
| `/check-lease`, `/evals`, `/about` | 87 to 88 | 420 to 450 ms |

Accessibility, best practices and SEO were 100 everywhere. In a real browser the chat page's largest paint is at 160 ms and the console is clean; Lighthouse's 2.1 s to 3.1 s LCP is its simulation charging the page for the JavaScript that loads beside it, not a late paint.

## What moved it

| Change | Effect |
| --- | --- |
| The italic face in a font of its own, loaded only when emphasised text is on the page, instead of preloaded with every page (47 KB) | Chat LCP 2.3 s to 1.7 s, performance 81 to 83 |
| The source panel (a Dialog, Tabs and their positioning code) as a lazy chunk, loaded on the first source or trace opened | The other pages' blocking time 420–450 ms to 250–350 ms, performance 88 to 93 |
| The Markdown renderer as a lazy chunk, with both chunks started when the question is focused or asked, so they have arrived by the time an answer has | Chat blocking time 630 ms to 520 ms, 35 KB less JavaScript on load |

The two lazy chunks use `next/dynamic` with `ssr: false`; without it Next lists their scripts in every page's HTML. Total JavaScript shipped rose by about 10 KB (each chunk compresses on its own), so the budget moved from 365 to 375 kB; what a first paint loads fell by about 40 KB.

## What is left

The chat page stays near 80. An experiment that removed the AI SDK from it (a stub in place of `useChat`) scored 86 with 150 ms less blocking time, so the SDK and zod (which it needs) are a third of the gap. The rest is React's hydration of the shell and the composer (the form library and the combobox) and the framework's own runtime, which `/about` pays too and still reaches 93.

The lever that would close it is loading the chat engine (`useChat` and its transport) on the first interaction, with the composer and the empty state rendered without it. That means two composers, one before and one after the engine loads, with the filters carried across and focus moved to the new text area: more moving parts than the gain justifies while the gate (desktop, 100) and three of four pages on mobile pass. It is the next step if the chat page's mobile score has to reach 90.

## Reporting

`pnpm run lighthouse` now runs two passes over every page: the desktop preset (`lighthouserc.json`), where all four categories must stay at or above 90, and Lighthouse's default phone emulation (`lighthouserc.mobile.json`), where accessibility, best practices and SEO must stay at or above 90 and performance is reported as a warning, so the chat page's 80 shows up in every run instead of being hidden.

## Reproduce

```bash
cd apps/web
pnpm run build
pnpm run lighthouse     # both passes; the mobile warning names the chat page
```

For repeated runs, `pnpm exec lhci autorun` with a config that sets `numberOfRuns` to 5 gives medians; the page-to-page spread of a single run is as large as most of these changes.
