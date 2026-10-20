import a2 from "@/test/fixtures/evals/results/A2/dev.json";

import {
  byConfigOrder,
  estimate,
  headlineRun,
  secondJudge,
  evalRunSchema,
  formatInterval,
  formatLatency,
  formatUsd,
  groupMeans,
  percentile,
  runCost,
  type EvalRun,
} from "./evals";

const run: EvalRun = evalRunSchema.parse(a2);

function withResults(results: EvalRun["results"]): EvalRun {
  return { ...run, n_items: results.length, results };
}

describe("evalRunSchema", () => {
  it("reads a results file as rag_eval writes it", () => {
    expect(run.config_name).toBe("A2");
    expect(run.results).toHaveLength(24);
  });

  it("refuses a file from another schema version", () => {
    expect(() => evalRunSchema.parse({ ...a2, schema_version: 2 })).toThrow();
  });
});

describe("estimate", () => {
  it("reads a metric's mean, interval and count from the summary", () => {
    const summary = {
      faithfulness: 0.9,
      "faithfulness.low": 0.7,
      "faithfulness.high": 0.97,
      "faithfulness.n": 20,
    };
    expect(estimate(summary, "faithfulness")).toEqual({ value: 0.9, low: 0.7, high: 0.97, n: 20 });
  });

  it("is null for a metric that applied to no item", () => {
    expect(estimate({ mrr: null, "mrr.n": 0 }, "mrr")).toBeNull();
    expect(estimate({}, "mrr")).toBeNull();
  });
});

describe("formatting", () => {
  it("writes an interval with an en dash, or nothing without one", () => {
    expect(formatInterval(0.651, 0.8749)).toBe("0.65–0.87");
    expect(formatInterval(null, 0.9)).toBeNull();
  });

  it("writes latency in seconds from one second up", () => {
    expect(formatLatency(640.4)).toBe("640 ms");
    expect(formatLatency(3140)).toBe("3.1 s");
  });

  it("shows a fraction of a cent to four places", () => {
    expect(formatUsd(0.0042)).toBe("$0.0042");
    expect(formatUsd(1.374)).toBe("$1.37");
    expect(formatUsd(0)).toBe("$0.00");
  });
});

describe("percentile", () => {
  it("takes the nearest rank, an observed value", () => {
    const values = Array.from({ length: 20 }, (_, i) => i + 1);
    expect(percentile(values, 0.95)).toBe(19);
    expect(percentile(values, 0.5)).toBe(10);
    expect(percentile([7], 0.95)).toBe(7);
    expect(percentile([], 0.5)).toBeNull();
  });
});

describe("runCost", () => {
  it("counts only the items whose latency and cost were recorded", () => {
    const base = run.results[0]!;
    const cost = runCost(
      withResults([
        { ...base, latency_ms: 1000, cost_usd: 0.002 },
        { ...base, latency_ms: 3000, cost_usd: 0.004 },
        { ...base, latency_ms: null, cost_usd: null },
      ]),
    );
    expect(cost).toMatchObject({ p50Ms: 1000, p95Ms: 3000, timed: 2, costed: 2 });
    expect(cost.perQuestionUsd).toBeCloseTo(0.003);
    expect(cost.totalUsd).toBeCloseTo(0.006);
  });

  it("has no figures when nothing was recorded", () => {
    const base = run.results[0]!;
    expect(runCost(withResults([{ ...base, latency_ms: null, cost_usd: null }]))).toMatchObject({
      p95Ms: null,
      perQuestionUsd: null,
      totalUsd: null,
    });
  });
});

describe("groupMeans", () => {
  it("groups items by their id's jurisdiction, in the fixed order, then the rest", () => {
    const rows = groupMeans(run, ["recall@5"]);
    expect(rows.map((row) => row.group.name)).toEqual([
      "Dubai",
      "Spain",
      "Colombia",
      "Florida",
      "Across jurisdictions",
      "Out of scope",
    ]);
    expect(rows[0]?.group.code).toBe("AE-DU");
  });

  it("averages a metric over the items where it applies, with that count", () => {
    const base = run.results[0]!;
    const rows = groupMeans(
      withResults([
        { ...base, item_id: "fl-0001", metrics: { correctness: 1 } },
        { ...base, item_id: "fl-0002", metrics: { correctness: 0 } },
        { ...base, item_id: "fl-0003", metrics: { correctness: null } },
      ]),
      ["correctness", "recall@5"],
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ items: 3, means: { correctness: { value: 0.5, n: 2 } } });
    expect(rows[0]?.means["recall@5"]).toBeUndefined();
  });
});

describe("headlineRun", () => {
  it("leads with the configuration the site serves, then A2, then any judged run", () => {
    const named = (config_name: string, judged = true) => ({ ...run, config_name, judged });
    expect(headlineRun([named("A2"), named("A2-claude")])?.config_name).toBe("A2-claude");
    expect(headlineRun([named("A0", false), named("A2")])?.config_name).toBe("A2");
    expect(headlineRun([named("A0", false), named("LC")])?.config_name).toBe("LC");
    expect(headlineRun([named("A0", false)])).toBeUndefined();
  });
});

describe("secondJudge", () => {
  it("reads the second judge's agreement per criterion", () => {
    expect(secondJudge(run)).toEqual([
      { criterion: "faithfulness", agreement: { value: 0.9, low: 0.699, high: 0.9721, n: 20 } },
      { criterion: "correctness", agreement: { value: 0.85, low: 0.6396, high: 0.9476, n: 20 } },
    ]);
    expect(secondJudge({ ...run, summary: {} })).toEqual([]);
  });
});

describe("byConfigOrder", () => {
  it("puts each Claude twin right after its configuration", () => {
    const names = ["LC-claude", "A2-claude", "LC", "A0", "A2"].map((config_name) => ({
      ...run,
      config_name,
    }));
    expect(names.sort(byConfigOrder).map((r) => r.config_name)).toEqual([
      "A0",
      "A2",
      "A2-claude",
      "LC",
      "LC-claude",
    ]);
  });

  it("follows the ablation plan, then names it does not know", () => {
    const names = ["LC", "Z9", "A2", "A0", "B1"].map((config_name) => ({ ...run, config_name }));
    expect(names.sort(byConfigOrder).map((r) => r.config_name)).toEqual([
      "A0",
      "A2",
      "LC",
      "B1",
      "Z9",
    ]);
  });
});
