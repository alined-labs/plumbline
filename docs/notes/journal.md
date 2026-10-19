# Journal

Dated working notes: what was tried, what was learned, what changed course. Newest first. Decisions that last go into an ADR; this is the trail that led to them.

## 2026-10-19: the design system, before the build

- The Alined design system went into the seed before any lane started, so the front end is built on it from the first task and the placeholder token layer and Phase DS are gone.
- The tokens live once, in `apps/web/design/tokens.json` (W3C design tokens format, light and dark); `tokens.css`, the Tailwind theme and the contrast report are generated from it, and a unit test fails if they drift, if a colour pair falls under its WCAG 2.2 minimum, or if two colours that must be told apart come closer than 7 CIEDE2000, under normal vision and three simulated deficiencies.
- The theme resets Tailwind's colours, type sizes, radii, shadows and easings, so a class outside the system compiles to nothing instead of drifting.
- The logo is drawn with its own `brand` tokens: the accent turns lavender in the dark theme, and the bob disappeared against it. Focus on the inverse surface (the toast) has its own ring for the same reason.
- Fonts are self-hosted (Atkinson Hyperlegible Next and Mono, Source Serif 4 for the statutes' own words), icons are vendored from Lucide, and no dependency was added.

## 2026-10-19: the seed

- Cut the seed: the uv and pnpm workspaces, the frozen contracts (`core/types.py`, `core/config.py`, `core/stream.py`, `rag_eval/schema.py`), the record/replay cache, the statistics helpers, a stub pipeline that streams every part of the answer protocol, the static Next.js shell on placeholder tokens, and the gates (`make check-py`, `check-web`, `check-docs`, CI with gitleaks).
- The stream contract is pinned by a fixture: the exact bytes the stub streams are committed in `packages/ts-client/fixtures/ask-stub.sse`, and both the API tests and the browser tests read them.
- Chose pypdfium2 over PyMuPDF for page rendering and citation boxes: same capability, and its licence keeps the code Apache-2.0 clean (PyMuPDF is AGPL).
- Seven-day release-age policy on both ecosystems (`exclude-newer` for uv, `minimumReleaseAge` for pnpm).
