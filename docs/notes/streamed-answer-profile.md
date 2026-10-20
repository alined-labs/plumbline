# Profile of the streamed answer

How much work the browser does while an answer streams, where it went, and what changed. Measured on 2026-10-20 on MX3 (Intel Core i5-13420H, 12 threads), Chromium from Playwright, against the static export.

## Method

- **The answer.** `apps/web/e2e/profile-stream.mjs` replaces `/api/ask` in the page with a long synthetic answer dripped through the real SSE parser: 401 word deltas 12 ms apart (five paragraphs, a list and five verified citations), the status parts before it and the citation, answer and trace parts after it. That is longer and faster than the stub, and close to what the generator is expected to send.
- **React's work.** React's `<Profiler>` wraps the chat (`ChatProfiler`). It records only in an export built with `NEXT_PUBLIC_PROFILE=1 next build --profile`; in every other build the condition is a constant and the minifier removes it. Each commit's `actualDuration` is summed from the click on Send to the moment "Answered in" appears.
- **The page.** Long tasks (`PerformanceObserver`), frame gaps (`requestAnimationFrame`), and the time to the finished answer, stamped in the page by a `MutationObserver`.
- **The device.** Each variant ran five times at the CPU's own speed (1×) and five times with the CPU slowed 4× through the DevTools protocol, roughly a mid-range phone. The tables give the medians.

## Results

| Variant | CPU | Commits | React work | Commit p50 / p95 / max | Finished in |
| --- | --- | ---: | ---: | --- | ---: |
| A: every delta re-renders the chat | 1× | 417 | 752 ms | 1.6 / 3.1 / 16.3 ms | 5.40 s |
| D: the three changes below | 1× | 113 | 139 ms (−82%) | 0.7 / 3.0 / 16.5 ms | 5.40 s |
| A: every delta re-renders the chat | 4× | 417 | 2,264 ms | 4.6 / 9.9 / 54.4 ms | 7.60 s |
| D: the three changes below | 4× | 132 | 572 ms (−75%) | 2.9 / 11.3 / 47.5 ms | 6.72 s |

At 1× the stream's own pace sets the finish (401 × 12 ms plus the other parts is about 5.1 s), so both variants finish together and the saving is idle time. At 4× variant A keeps the main thread busy enough to delay the stream itself, and D finishes 0.9 s sooner (A ranged from 7.24 to 8.05 s across runs, D from 6.46 to 6.80 s). No variant produced more than one long task or more than two frames over 50 ms.

Each change was measured on its own at 4× (three runs, React work only): throttling alone took React's work from 2,204 to 1,124 ms; rendering the Markdown block by block took it to 969 ms; memoizing the composer took it to 556 ms.

## What the work was

A Chrome trace of variant A at 4× split the main thread's time into React's reconciliation (about 2.7 s of self time in react-dom), the shared chunk that holds react-markdown, the AI SDK and zod (about 2.6 s: micromark's tokenizer re-parsing the whole answer, and zod validating every chunk of the stream), and native work (about 3.2 s), against 1.3 s of style, layout and paint. Three things made each delta cost more than it needed to:

1. **Every delta was a commit.** `useChat` published each of the 401 deltas.
2. **Every commit re-parsed the whole answer.** react-markdown parses its whole input on each render, so the cost of a delta grew with the answer.
3. **Every commit re-rendered the composer.** The chat re-renders on each update, and the composer (React Hook Form, the Base UI combobox, the date field) re-rendered with it, because its callback props were new functions each time.

## What changed

1. `useChat({ throttle: 50 })`: messages are published at most every 50 ms. The AI SDK still processes every part as it arrives, runs its callbacks without delay, and publishes the final messages before the status becomes ready, so the status steps, the announcement and the finished answer are unaffected.
2. `AnswerBody` renders each Markdown block (split at blank lines, which is where Markdown blocks end) as a memoized component, compared by its text and the citations' identities. While an answer streams only its last block changes, so earlier paragraphs are parsed once.
3. `Composer` is memoized, compared by `busy` and `disabledReason`. The callbacks are left out of the comparison: the chat rebuilds them each render with the same behaviour, since they reach only refs and the one `useChat` instance.

## What is left

- The largest commits (up to about 48 ms at 4×) are the first, when the answer replaces the skeleton, and the last, when the meta line, the source cards and the announcement arrive together. They happen once per answer.
- The AI SDK validates every stream chunk against its schema with zod. That is its own work, outside React, and it is what keeps variant D from finishing at the stream's pace at 4×.

## Reproduce

```bash
cd apps/web
NEXT_PUBLIC_PROFILE=1 pnpm exec next build --profile   # an export with React's profiling build
node e2e/serve.mjs out 3100 &                          # serve it
node e2e/profile-stream.mjs http://127.0.0.1:3100 4 5  # CPU slowdown 4×, five runs
pnpm run build                                         # back to the normal export
```

The script prints each run and the medians as JSON. Variant A is the same code with `throttle` removed from `useChat` and `AnswerBody` and `Composer` as they were before this change.
