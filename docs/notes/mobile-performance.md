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

## The chat engine on first use (E7c)

The lever named here before is now pulled, without the two composers it seemed to need. The chat page is a light shell (the empty state, the composer and the usage meter) and a separate engine chunk (`components/chat/chat-engine.tsx`: `useChat`, the AI SDK's transport and the conversation). The shell owns the one composer; the engine mounts when the first question is sent, asks it, and from then on the composer drives it through a ref (`ask`, `stop`) while the engine reports back only what the composer shows (busy, the quota's words). The engine's chunk starts loading when the question box is focused, with the answer's other chunks, so in practice it has arrived before the question is sent; until it mounts, the question waits under the answer skeleton.

The composer's validation moved from a zod schema through `@hookform/resolvers` to a plain resolver in `lib/ask-form.ts` (the same three rules and messages), so the page's first load carries no zod at all. The lease page still uses zod for its form; its transport was already loaded on the first check.

Five mobile runs each, the chat page on the static export:

| Build | Performance (runs) | Median | Total blocking time | LCP |
| --- | --- | ---: | ---: | ---: |
| main before E7c | 78, 79, 82, 83, 84 | 82 | 560 ms | 3.1 s |
| the engine on first use | 84, 85, 85, 88, 89 | 85 | 412 ms | 2.9 s |
| and no zod in the composer | 90, 90, 91, 91, 92 | 91 | 292 ms | 2.7 s |

What a first load of the chat page fetches fell from 304 kB to 224 kB of JavaScript (brotli, the 18 scripts its HTML names, without the polyfills that only browsers without modules load). The total the export ships rose from 395.6 to 405.4 kB, because each lazy chunk compresses on its own and the engine now shares less with the rest; the size budget, which counts every chunk, moves from 400 to 410 kB for that reason.

What remains is React's hydration of the shell (its single largest chunk, about 0.8 s of script on the 4× slowed CPU) and the framework's runtime, which every page pays.

## Budgets

Two budgets, because they answer different questions. `.size-limit.json` holds the JavaScript the export ships, every chunk included, lazy ones and the polyfills that only browsers without modules load: it grows with each feature that loads on demand, so it is a ceiling against waste rather than a measure of speed. `e2e/budget.spec.ts` holds what each page loads before anyone touches it, brotli compressed as Cloudflare Pages serves it, counted up to the load event (after it the sidebar prefetches the other pages at low priority). Measured on 2026-10-20, with the chat engine loaded on first use: the chat page 223.5 kB (303.9 kB before), the lease page 246.1 kB, `/evals` and `/about` 191.8 kB each; each budget sits about 5% above its page.

## Reporting

`pnpm run lighthouse` now runs two passes over every page: the desktop preset (`lighthouserc.json`), where all four categories must stay at or above 90, and Lighthouse's default phone emulation (`lighthouserc.mobile.json`), where accessibility, best practices and SEO must stay at or above 90 and performance is reported as a warning: single runs spread by about five points, so a hard 90 would fail on noise.

## Reproduce

```bash
cd apps/web
pnpm run build
pnpm run lighthouse     # both passes; the mobile warning names the chat page
```

For repeated runs, `pnpm exec lhci autorun` with a config that sets `numberOfRuns` to 5 gives medians; the page-to-page spread of a single run is as large as most of these changes.
