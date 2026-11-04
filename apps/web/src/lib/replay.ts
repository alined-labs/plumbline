import type { AnswerSummary, Citation, Jurisdiction, TraceSummary } from "@plumbline/ts-client";
import { queryOptions } from "@tanstack/react-query";

import { DISCLAIMER } from "./copy";
import type { PlumblineMessage } from "./messages";

// The static tier's replay: answers Plumbline recorded for the benchmark's development
// questions (evals/replay/<config>/dev.jsonl, written by Lane A's runner), shown through the
// same answer view as a live one. Read at build time into /replay.json.

/** A stored answer, as plumbline.core.types.Answer writes it. */
export type ReplayAnswer = {
  text: string;
  status: AnswerSummary["status"];
  citations: Citation[];
  jurisdictions: Jurisdiction[];
  as_of: string | null;
  confidence: number | null;
  abstain_reason: string | null;
  invalid_citations: number;
};

export type ReplayItem = {
  item_id: string;
  question: string;
  jurisdictions: Jurisdiction[];
  as_of: string | null;
  answer: ReplayAnswer;
  trace: {
    model: string;
    route: string;
    timings_ms: Record<string, number>;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    cached: boolean;
  };
};

export type ReplayFile = {
  /** The configuration that answered, or null when no run has been stored yet. */
  config: string | null;
  config_hash: string | null;
  items: ReplayItem[];
};

/** The marker Lane B's dataset export and Lane A's replay put in place of a quote from a
 * source that is not redistributed (the Dubai and Colombian texts): corpus/export.py WITHHELD. */
const WITHHELD_PREFIX = "[Withheld:";

export function isWithheld(quote: string): boolean {
  return quote.startsWith(WITHHELD_PREFIX);
}

/** A stored answer as the two messages a live answer leaves behind: the question, then the
 * answer's text with its citations, summary and trace as the stream's data parts. The trace
 * has no request id, so the answer offers no feedback: there is no request to attach it to. */
export function toMessages(
  item: ReplayItem,
  config: string,
  configHash: string,
): PlumblineMessage[] {
  const { answer, trace } = item;
  const summary: AnswerSummary = {
    status: answer.status,
    jurisdictions: answer.jurisdictions,
    as_of: answer.as_of,
    confidence: answer.confidence,
    abstain_reason: answer.abstain_reason,
    invalid_citations: answer.invalid_citations,
    disclaimer: DISCLAIMER,
  };
  const traceSummary: TraceSummary = {
    request_id: "",
    config_name: config,
    config_hash: configHash,
    route: trace.route,
    model: trace.model,
    tier: "static",
    timings_ms: trace.timings_ms,
    input_tokens: trace.input_tokens,
    output_tokens: trace.output_tokens,
    cost_usd: trace.cost_usd,
    cached: trace.cached,
    trace_url: null,
  };
  return [
    { id: `${item.item_id}-q`, role: "user", parts: [{ type: "text", text: item.question }] },
    {
      id: `${item.item_id}-a`,
      role: "assistant",
      parts: [
        { type: "text", text: answer.text, state: "done" },
        ...answer.citations.map((citation) => ({
          type: "data-citation" as const,
          data: citation,
        })),
        { type: "data-answer" as const, data: summary },
        { type: "data-trace" as const, data: traceSummary },
      ],
    },
  ];
}

/** The stored answers as the export holds them (/replay.json), fetched only when the page is
 * paused or an answer has failed. An export built before any run was stored holds none. */
export function replayQuery() {
  return queryOptions({
    queryKey: ["replay"],
    queryFn: async (): Promise<ReplayFile> => {
      const response = await fetch("/replay.json");
      if (!response.ok) throw new Error(`/replay.json answered ${response.status}`);
      return (await response.json()) as ReplayFile;
    },
    staleTime: Infinity,
    retry: false,
  });
}
