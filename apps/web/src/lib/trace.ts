import type { TraceSummary } from "@plumbline/ts-client";

// The TraceWaterfall spec's spans, from the stream's data-trace part. The part carries each
// stage's duration by name and no start times; the stages run one after another, so each
// starts where the one before it ended.

export type SpanKind = "retrieval" | "model" | "verification" | "other";

export type TraceSpan = {
  name: string;
  kind: SpanKind;
  /** Milliseconds from the start of the answer. */
  start: number;
  duration: number;
  /** Replayed from a recording rather than run: drawn as an outline. */
  cached: boolean;
  failed: boolean;
};

const LABELS: Record<string, string> = {
  detect: "Reading your question",
  retrieve: "Searching the statutes",
  keyword: "Keyword search",
  vector: "Vector search",
  fusion: "Fusing the rankings",
  rerank: "Ranking passages",
  generate: "Writing the answer",
  verify: "Checking citations",
};

function kindOf(stage: string): SpanKind {
  if (/retriev|search|keyword|vector|fusion|bm25/.test(stage)) return "retrieval";
  if (/generat|model|llm|write|answer/.test(stage)) return "model";
  if (/verif|cite|citation/.test(stage)) return "verification";
  return "other";
}

/** "generate" → "Writing the answer"; an unknown stage keeps its own name, in sentence case. */
export function stageLabel(stage: string): string {
  const known = LABELS[stage];
  if (known) return known;
  const words = stage.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function spansFromTrace(trace: Pick<TraceSummary, "timings_ms" | "cached">): {
  spans: TraceSpan[];
  total: number;
} {
  let start = 0;
  const spans = Object.entries(trace.timings_ms).map(([stage, duration]) => {
    const span: TraceSpan = {
      name: stageLabel(stage),
      kind: kindOf(stage),
      start,
      duration,
      cached: trace.cached,
      failed: false,
    };
    start += duration;
    return span;
  });
  return { spans, total: start };
}

/** "412 ms" under a second, "4.2 s" above, the way the content rules write durations. */
export function duration(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** "$0.0042": a cost in US dollars, with the cents a model call needs to show up. */
export function dollars(amount: number): string {
  return `$${amount.toFixed(amount < 0.01 ? 4 : 2)}`;
}

/** "9f7d…6dd7": the head and tail of an ID, with the full value kept elsewhere (a title). */
export function middleTruncate(value: string, keep = 4): string {
  return value.length <= keep * 2 + 1 ? value : `${value.slice(0, keep)}…${value.slice(-keep)}`;
}
