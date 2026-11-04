# The demo recording

`demo.spec.ts` walks Plumbline's demo storyline at reading pace with captions and records it as video: a cited answer, the article in the source panel, the trace with its cost, a question it declines, a lease checked clause by clause, and the evaluation page. It is not a test and the gate does not run it.

## Rehearse on this build

```bash
cd apps/web
pnpm build
pnpm exec playwright test -c demo/playwright.demo.config.ts
./demo/make-media.sh
```

Without `DEMO_URL` the script serves this build's export and answers from the API's recorded stub stream, so the words on screen are the stub's, not legal information. The video lands in `test-results/demo/`, which git ignores.

## Record the live site

```bash
DEMO_URL=https://plumbline.alinedlabs.co pnpm exec playwright test -c demo/playwright.demo.config.ts
DEMO_URL=https://plumbline.alinedlabs.co DEMO_THEME=dark pnpm exec playwright test -c demo/playwright.demo.config.ts
./demo/make-media.sh
```

The live run asks two real questions and checks one invented lease, so it uses three of the day's demo allowance and the API's model calls. `make-media.sh` writes `test-results/demo-media/plumbline-demo.mp4` (the whole walk-through, H.264) and `plumbline-demo.gif` (its first 90 seconds at 10 frames a second, 800 px wide, for the README). Watch the video before publishing it: the answer on screen is whatever the live pipeline wrote that day.
