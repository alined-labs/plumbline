import { z } from "zod";

import { JURISDICTION_IDS, jurisdictionInfo } from "./jurisdictions";

// The evaluation page's data: Lane A's results files (rag_eval.schema.EvalRun), Lane C's
// judge agreement table and the CI gate's thresholds, all read at build time. Only the fields
// the page shows are parsed; a results file that does not fit fails the build, so a page
// never shows a number it misread.

const metricMap = z.record(z.string(), z.number().nullable());

const resultSchema = z.object({
  item_id: z.string(),
  metrics: metricMap.default({}),
  latency_ms: z.number().nonnegative().nullish(),
  cost_usd: z.number().nonnegative().nullish(),
});

export const evalRunSchema = z.object({
  schema_version: z.literal(1),
  run_id: z.string(),
  config_name: z.string(),
  config_hash: z.string(),
  git_sha: z.string(),
  golden_file: z.string(),
  split: z.enum(["dev", "test", "all"]),
  created_at: z.iso.datetime({ offset: true }),
  judged: z.boolean(),
  n_items: z.number().int().nonnegative(),
  results: z.array(resultSchema),
  summary: metricMap,
  notes: z.string().nullish(),
});

export type EvalRun = z.infer<typeof evalRunSchema>;

const rateSchema = z.object({
  hits: z.number().int().nonnegative(),
  total: z.number().int().nonnegative(),
  low: z.number(),
  high: z.number(),
});

/** Lane C's judge calibration (judge/calibration.py's Agreement as JSON), one set per source
 * of labels: the constructed 50 correct and 50 with planted errors, and the human's own. */
export const agreementSchema = z.object({
  judge_model: z.string(),
  created_at: z.iso.datetime({ offset: true }),
  bar: z.number(),
  sets: z.array(
    z.object({
      labels: z.enum(["constructed", "human"]),
      description: z.string(),
      criteria: z.array(z.object({ criterion: z.string(), tpr: rateSchema, tnr: rateSchema })),
    }),
  ),
});

export type Agreement = z.infer<typeof agreementSchema>;
export type Rate = z.infer<typeof rateSchema>;

type Direction = "higher" | "lower";
type MetricInfo = { label: string; group: "retrieval" | "answers"; better: Direction };

/** Every metric the page knows, in the order the tables show them. Names are rag_eval's
 * (metrics.py) and the judge's (faithfulness, correctness). */
export const METRICS = {
  "recall@5": { label: "Recall@5", group: "retrieval", better: "higher" },
  "recall@20": { label: "Recall@20", group: "retrieval", better: "higher" },
  mrr: { label: "MRR", group: "retrieval", better: "higher" },
  "ndcg@10": { label: "nDCG@10", group: "retrieval", better: "higher" },
  "jurisdiction@5": { label: "Right jurisdiction@5", group: "retrieval", better: "higher" },
  citation_precision: { label: "Citation precision", group: "answers", better: "higher" },
  citation_validity: { label: "Citation validity", group: "answers", better: "higher" },
  faithfulness: { label: "Faithfulness", group: "answers", better: "higher" },
  correctness: { label: "Correctness", group: "answers", better: "higher" },
  abstention_accuracy: { label: "Abstention accuracy", group: "answers", better: "higher" },
  false_abstention: { label: "False abstention", group: "answers", better: "lower" },
  partial_accuracy: { label: "Partial marked", group: "answers", better: "higher" },
} as const satisfies Record<string, MetricInfo>;

export type MetricName = keyof typeof METRICS;

export const RETRIEVAL_METRICS = (Object.keys(METRICS) as MetricName[]).filter(
  (name) => METRICS[name].group === "retrieval",
);
export const ANSWER_METRICS = (Object.keys(METRICS) as MetricName[]).filter(
  (name) => METRICS[name].group === "answers",
);

/** The headline metrics, in the Metric spec's order (latency and cost follow them). */
export const HEADLINE_METRICS = [
  "citation_precision",
  "faithfulness",
  "abstention_accuracy",
] as const satisfies readonly MetricName[];

/** Where the headline numbers come from, first found first: the configuration the public site
 * answers with (A2 with Claude Sonnet generating), then A2 itself, until Lane A's failure
 * analysis names the default (A12). */
export const HEADLINE_CONFIGS = ["A2-claude", "A2"] as const;

export function headlineRun(runs: readonly EvalRun[]): EvalRun | undefined {
  for (const name of HEADLINE_CONFIGS) {
    const run = runs.find((candidate) => candidate.config_name === name);
    if (run) return run;
  }
  return runs.find((run) => run.judged);
}

/** A configuration's Claude-generated twin ("A2-claude"): the same retrieval, with Claude
 * Sonnet writing the answers as the public site does. */
const CLAUDE = "-claude";

export function baseConfig(name: string): { base: string; claude: boolean } {
  return name.endsWith(CLAUDE)
    ? { base: name.slice(0, -CLAUDE.length), claude: true }
    : { base: name, claude: false };
}

/** The ablation plan's order, each Claude twin right after its configuration; a configuration
 * the plan does not name goes last, by name. */
const CONFIG_ORDER = ["A0", "A1", "A2", "A3", "A4", "A5", "A6", "E1", "R1", "LC"];

export function byConfigOrder(a: EvalRun, b: EvalRun): number {
  const rank = (run: EvalRun) => {
    const { base, claude } = baseConfig(run.config_name);
    const at = CONFIG_ORDER.indexOf(base);
    return (at === -1 ? CONFIG_ORDER.length : at) * 2 + (claude ? 1 : 0);
  };
  return rank(a) - rank(b) || a.config_name.localeCompare(b.config_name);
}

/** The criteria a judge scores. */
export const JUDGED = ["faithfulness", "correctness"] as const satisfies readonly MetricName[];

/** How often a second judge agreed with the first, per criterion, as the runner writes it:
 * 'second_judge.<criterion>' with its interval and count. Empty when the run has none. */
export function secondJudge(run: EvalRun) {
  return JUDGED.flatMap((criterion) => {
    const agreement = estimate(run.summary, `second_judge.${criterion}`);
    return agreement ? [{ criterion, agreement }] : [];
  });
}

export type Estimate = { value: number; low: number | null; high: number | null; n: number };

/** One metric of a run as summarize() wrote it: the mean, its 95% interval and how many items
 * it was computed on. Null when the metric did not apply to any item. */
export function estimate(summary: Record<string, number | null>, name: string): Estimate | null {
  const value = summary[name];
  if (value === null || value === undefined) return null;
  return {
    value,
    low: summary[`${name}.low`] ?? null,
    high: summary[`${name}.high`] ?? null,
    n: summary[`${name}.n`] ?? 0,
  };
}

const twoPlaces = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Scores are shares from 0 to 1, shown to two places. */
export function formatScore(value: number): string {
  return twoPlaces.format(value);
}

/** "0.76–0.87", or null without an interval. */
export function formatInterval(low: number | null, high: number | null): string | null {
  if (low === null || high === null) return null;
  return `${formatScore(low)}–${formatScore(high)}`;
}

/** The value at a share of a sorted list by the nearest-rank method: p95 of 20 items is the
 * 19th, an observed latency rather than one interpolated between two. */
export function percentile(values: readonly number[], share: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const rank = Math.max(1, Math.ceil(share * sorted.length));
  return sorted[rank - 1] ?? null;
}

export type RunCost = {
  p50Ms: number | null;
  p95Ms: number | null;
  /** Mean over the items whose cost was recorded. */
  perQuestionUsd: number | null;
  totalUsd: number | null;
  /** Items with a recorded latency and cost, out of the run's results. */
  timed: number;
  costed: number;
};

/** Latency and cost of a run, from its per-item records. */
export function runCost(run: EvalRun): RunCost {
  const latencies = run.results.flatMap((r) => (r.latency_ms == null ? [] : [r.latency_ms]));
  const costs = run.results.flatMap((r) => (r.cost_usd == null ? [] : [r.cost_usd]));
  const total = costs.reduce((sum, cost) => sum + cost, 0);
  return {
    p50Ms: percentile(latencies, 0.5),
    p95Ms: percentile(latencies, 0.95),
    perQuestionUsd: costs.length ? total / costs.length : null,
    totalUsd: costs.length ? total : null,
    timed: latencies.length,
    costed: costs.length,
  };
}

/** "3.1 s", or "640 ms" under a second. */
export function formatLatency(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 }).format(ms / 1000)} s`;
}

/** Dollars with enough places to show a fraction of a cent: "$0.0042", "$1.37". */
export function formatUsd(usd: number): string {
  const digits = usd !== 0 && Math.abs(usd) < 0.01 ? 4 : 2;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(usd);
}

/** The golden set's item id prefixes, one per jurisdiction ("fl-0007"). */
const PREFIX = {
  dubai: "du",
  spain: "es",
  colombia: "co",
  florida: "fl",
} as const satisfies Record<(typeof JURISDICTION_IDS)[number], string>;

export type Group = { prefix: string; code: string | null; name: string };

/** The golden set's groups as its item ids name them: the four jurisdictions in their fixed
 * order, then the cross-jurisdiction and the out-of-scope items. */
export const GROUPS: Group[] = [
  ...JURISDICTION_IDS.map((id) => {
    const { code, name } = jurisdictionInfo(id);
    return { prefix: PREFIX[id], code, name };
  }),
  { prefix: "xj", code: null, name: "Across jurisdictions" },
  { prefix: "oos", code: null, name: "Out of scope" },
];

export type GroupRow = {
  group: Group;
  items: number;
  /** Mean of each metric over the group's items where it applies, with that count. */
  means: Partial<Record<MetricName, { value: number; n: number }>>;
};

/** Per-group means of a run's metrics. Descriptive only: a group of 30 items or fewer gives
 * intervals too wide to compare groups, so the page shows means and counts and says so. */
export function groupMeans(run: EvalRun, metrics: readonly MetricName[]): GroupRow[] {
  return GROUPS.flatMap((group) => {
    const results = run.results.filter((r) => r.item_id.split("-", 1)[0] === group.prefix);
    if (results.length === 0) return [];
    const means: GroupRow["means"] = {};
    for (const name of metrics) {
      const values = results.flatMap((r) => {
        const value = r.metrics[name];
        return value == null ? [] : [value];
      });
      if (values.length) {
        means[name] = {
          value: values.reduce((sum, v) => sum + v, 0) / values.length,
          n: values.length,
        };
      }
    }
    return [{ group, items: results.length, means }];
  });
}

export type ChartPoint = {
  label: string;
  value: number;
  low: number | null;
  high: number | null;
  n: number;
};

/** One metric across runs, for the interval chart: the runs that measured it, in their order. */
export function chartPoints(runs: readonly EvalRun[], name: MetricName): ChartPoint[] {
  return runs.flatMap((run) => {
    const value = estimate(run.summary, name);
    return value ? [{ label: run.config_name, ...value }] : [];
  });
}

/** The chart's takeaway in a sentence: which configuration scores best, and whether its interval
 * clears the next one's, since overlapping intervals are not a measured difference. */
export function takeaway(points: readonly ChartPoint[], metric: MetricName): string {
  const lower = METRICS[metric].better === "lower";
  const ranked = [...points].sort((a, b) => (lower ? a.value - b.value : b.value - a.value));
  const [best, next] = ranked;
  if (!best) return "";
  const interval = formatInterval(best.low, best.high);
  const lead = `${best.label} scores ${lower ? "lowest" : "highest"}, ${formatScore(best.value)}${interval ? ` (95% CI ${interval})` : ""}.`;
  if (!next) return lead;
  const separated =
    best.low !== null &&
    best.high !== null &&
    next.low !== null &&
    next.high !== null &&
    (lower ? best.high < next.low : best.low > next.high);
  return separated
    ? `${lead} Its interval clears ${next.label}'s, the next best.`
    : `${lead} Its interval overlaps ${next.label}'s, so the two are not measurably apart.`;
}
