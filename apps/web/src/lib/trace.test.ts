import { dollars, duration, middleTruncate, spansFromTrace, stageLabel } from "./trace";

describe("spansFromTrace", () => {
  it("lays the stages end to end and classifies them", () => {
    const { spans, total } = spansFromTrace({
      cached: false,
      timings_ms: { detect: 200, retrieve: 900, rerank: 600, generate: 2300, verify: 200 },
    });
    expect(total).toBe(4200);
    expect(spans.map((s) => [s.name, s.kind, s.start, s.duration])).toEqual([
      ["Reading your question", "other", 0, 200],
      ["Searching the statutes", "retrieval", 200, 900],
      ["Ranking passages", "other", 1100, 600],
      ["Writing the answer", "model", 1700, 2300],
      ["Checking citations", "verification", 4000, 200],
    ]);
    expect(spans.every((s) => !s.cached && !s.failed)).toBe(true);
  });

  it("marks every span of a replayed answer as cached", () => {
    const { spans } = spansFromTrace({ cached: true, timings_ms: { generate: 0 } });
    expect(spans).toEqual([
      {
        name: "Writing the answer",
        kind: "model",
        start: 0,
        duration: 0,
        cached: true,
        failed: false,
      },
    ]);
  });
});

describe("formatting", () => {
  it("writes stage names, durations, costs and IDs for a reader", () => {
    expect(stageLabel("query_rewrite")).toBe("Query rewrite");
    expect(duration(412.4)).toBe("412 ms");
    expect(duration(4200)).toBe("4.2 s");
    expect(dollars(0.00415)).toBe("$0.0042");
    expect(dollars(0.5)).toBe("$0.50");
    expect(middleTruncate("9f7d3a21c0b4e5f66dd7")).toBe("9f7d…6dd7");
    expect(middleTruncate("req_1")).toBe("req_1");
  });
});
