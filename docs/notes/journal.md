# Journal

Dated working notes: what was tried, what was learned, what changed course. Newest first. Decisions that last go into an ADR; this is the trail that led to them.

## 2026-10-19: where CI's time goes

- Over the twelve latest successful CI runs (pull requests and `main`, 23:37 to 23:52 UTC), the `web` job sets the wall time: 102 s on average, from 65 to 134 s, rising as the app shell added pages and tests. `python` takes 74 s, the image job 43 s and gitleaks 6 s. With the hub's own local check in front, a branch reaches `main` a few minutes after its push.
- Inside `make check-web` (91 s on E1b's run), Lighthouse takes 50 s for four pages, about 12 s a page; the e2e suite 14 s for 18 tests; the static build 12.5 s; format, lint, types and unit tests 12 s together. Lighthouse grows with every page it audits: ten pages would take it about two minutes.
- Installing Playwright's Chromium costs 22 s a run: 12 s of apt packages and 8.5 s of downloads. A browser cache could save only the downloads, less its own restore time, so CI goes without one.
- In the `python` job, starting the ParadeDB service takes 17 to 24 s, `make check-py` 23 to 34 s and pip-audit 15 to 20 s. Service containers start before any step runs, so their images cannot come from the Actions cache.
- On MX3, the e2e suites of Lane E's checkout, the hub's worktree and Lane P's all serve on port 3100, and Playwright reuses whatever server it finds there outside CI. The hub's check of PB2 failed that way at 23:45 UTC: every e2e test was refused once the other checkout's server stopped, while `main` was green on GitHub. One port per checkout would fix it; the file is Lane E's.

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
