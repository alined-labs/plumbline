// Profiles the streamed answer: React's commits (from the Profiler in ChatProfiler), long tasks,
// frame gaps and the time to the finished answer, on a slowed CPU. Not a test; see
// docs/notes/streamed-answer-profile.md for how to build the export it needs and what it found.
//   node e2e/profile-stream.mjs [baseUrl] [cpuSlowdown] [runs]
import { chromium } from "@playwright/test";

const baseUrl = process.argv[2] ?? "http://127.0.0.1:3100";
const slowdown = Number(process.argv[3] ?? 4);
const runs = Number(process.argv[4] ?? 3);

// Runs in the page before the app: a long answer (about 400 word deltas, 12 ms apart, five
// citations, a list) dripped through the real SSE parser in place of /api/ask, and the
// long-task and frame recorders.
function instrument() {
  const sentence = (n) =>
    `Under the statute the landlord must return the deposit within the time it sets, and any claim must be sent in writing with the reasons [${n}].`;
  const text = [1, 2, 3, 4, 5]
    .map((n) => Array.from({ length: 3 }, () => sentence(n)).join(" "))
    .join("\n\n")
    .concat(
      "\n\n- First point to check [1].\n- Second point to check [2].\n- Third point to check [3].",
    );
  const citation = (n) => ({
    type: "data-citation",
    id: `citation-${n}`,
    data: {
      n,
      chunk_id: `c-${n}`,
      ref: {
        jurisdiction: "florida",
        law: "fl-stat-83",
        article: `83.4${n}`,
        paragraph: null,
        edition: "2026",
      },
      label: `Fla. Stat. § 83.4${n}`,
      quote: "The landlord shall return the security deposit within 15 days.",
      gloss: null,
      language: "en",
      verified: true,
      page: null,
    },
  });
  const parts = [
    { type: "start", messageId: "msg_profile" },
    { type: "start-step" },
    { type: "data-status", data: { stage: "detecting", detail: null }, transient: true },
    { type: "data-status", data: { stage: "retrieving", detail: "40 passages" }, transient: true },
    { type: "data-status", data: { stage: "generating", detail: null }, transient: true },
    { type: "text-start", id: "answer-text" },
    ...text.split(/(?<= )/).map((delta) => ({ type: "text-delta", id: "answer-text", delta })),
    {
      type: "data-status",
      data: { stage: "verifying", detail: "5 of 5 verified" },
      transient: true,
    },
    ...[1, 2, 3, 4, 5].map(citation),
    {
      type: "data-answer",
      id: "answer",
      data: {
        status: "answered",
        jurisdictions: ["florida"],
        as_of: null,
        confidence: null,
        abstain_reason: null,
        invalid_citations: 0,
        disclaimer: "Legal information, not legal advice.",
      },
    },
    {
      type: "data-trace",
      id: "trace",
      data: {
        request_id: "r",
        config_name: "profile",
        config_hash: "0".repeat(64),
        route: "profile",
        model: "profile",
        tier: "full",
        timings_ms: {},
        input_tokens: 0,
        output_tokens: 0,
        cost_usd: 0,
        cached: true,
        trace_url: null,
      },
    },
    { type: "text-end", id: "answer-text" },
    { type: "finish-step" },
    { type: "finish", finishReason: "stop" },
  ];
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input.url;
    if (!url.includes("/api/ask")) return realFetch(input, init);
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      async start(controller) {
        for (const part of parts) {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(part)}\n\n`));
          await new Promise((resolve) => setTimeout(resolve, part.type === "text-delta" ? 12 : 20));
        }
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        controller.close();
      },
    });
    return new Response(body, {
      headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
    });
  };
  window.__deltas = parts.filter((part) => part.type === "text-delta").length;
  window.__longTasks = [];
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries())
      window.__longTasks.push({ at: entry.startTime, ms: entry.duration });
  }).observe({ type: "longtask" });
  // The finish is stamped in the page the moment the meta line appears, not when a polling
  // wait notices it.
  new MutationObserver(() => {
    if (window.__answeredAt === undefined && /Answered in/.test(document.body?.textContent ?? "")) {
      window.__answeredAt = performance.now();
    }
  }).observe(document, { childList: true, subtree: true, characterData: true });
  window.__frames = [];
  let last = performance.now();
  const frame = (now) => {
    window.__frames.push({ at: now, gap: now - last });
    last = now;
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

const percentile = (values, p) => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))] : 0;
};
const round = (value) => Math.round(value * 10) / 10;

const browser = await chromium.launch({
  executablePath: process.env.PW_CHROMIUM_PATH || undefined,
});
const results = [];
for (let run = 0; run < runs; run += 1) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: slowdown });
  await page.addInitScript(instrument);
  await page.goto(`${baseUrl}/`);
  await page
    .getByLabel("Your question")
    .fill("How long does my landlord have to return my deposit?");
  const started = await page.evaluate(() => {
    const at = performance.now();
    document.querySelector('button[aria-label="Send question"]').click();
    return at;
  });
  await page.getByText(/Answered in/).waitFor({ timeout: 120_000 });
  const sample = await page.evaluate((t0) => {
    const end = window.__answeredAt ?? performance.now();
    const inWindow = (at) => at >= t0 && at <= end;
    return {
      deltas: window.__deltas,
      streamMs: end - t0,
      commits: (window.__plumblineCommits ?? []).filter((c) => inWindow(c.at)),
      longTasks: window.__longTasks.filter((t) => inWindow(t.at)).map((t) => t.ms),
      gaps: window.__frames.filter((f) => inWindow(f.at)).map((f) => f.gap),
    };
  }, started);
  const commitMs = sample.commits.map((c) => c.actual);
  results.push({
    streamMs: round(sample.streamMs),
    commits: commitMs.length,
    reactMs: round(commitMs.reduce((a, b) => a + b, 0)),
    commitP50: round(percentile(commitMs, 0.5)),
    commitP95: round(percentile(commitMs, 0.95)),
    commitMax: round(Math.max(0, ...commitMs)),
    longTasks: sample.longTasks.length,
    longTaskMs: round(sample.longTasks.reduce((a, b) => a + b, 0)),
    framesOver50ms: sample.gaps.filter((gap) => gap > 50).length,
  });
  await page.close();
}
await browser.close();

const median = Object.fromEntries(
  Object.keys(results[0]).map((key) => [
    key,
    percentile(
      results.map((r) => r[key]),
      0.5,
    ),
  ]),
);
console.log(JSON.stringify({ baseUrl, slowdown, deltas: 401, runs: results, median }, null, 2));
