# Acceptance

The checks a release needs beyond the gate: every page as it first appears, in both themes, on a desktop and a phone (`screens.spec.ts`), and the demo's path through the real API (`live.spec.ts`). The gate does not run them: Playwright's default config reads `e2e/` only.

## On this build

```bash
cd apps/web
pnpm build
pnpm exec playwright test -c acceptance/playwright.acceptance.config.ts
```

The screens are compared with `baselines/export/`. A difference over 1% of the screen fails; the diff images land in `test-results/acceptance/`. When the change is meant, look at them, then take the new baselines with `--update-snapshots` and commit them with the change.

## On the live site

```bash
ACCEPT_URL=https://plumbline.alinedlabs.co ACCEPT_API_URL=https://plumbline-api.alinedlabs.co \
  pnpm exec playwright test -c acceptance/playwright.acceptance.config.ts
```

The live site keeps its own baselines in `baselines/live/` (its sidebar has the usage meter, its `/evals` the measured results); take them with `--update-snapshots` on the first run after a deploy and look at every one before committing it. `live.spec.ts` then asks one real question, checks one invented lease and reads `/evals`: two of the day's demo allowance and their model calls. It checks that the answer carries a verified citation, that its article opens in the panel, and that the API's visitor cookie was set and sent back across the two origins.
