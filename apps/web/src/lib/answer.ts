import type { AnswerSummary, Citation, TraceSummary } from "@plumbline/ts-client";

import { dataParts, messageText, type PlumblineMessage } from "./messages";

/** One assistant message, read for display. */
export type AnswerView = {
  /** The answer's Markdown, with each verified [n] turned into a link to #source-n and every
   * other [n] removed. */
  markdown: string;
  /** Verified citations, one per number, in the order the answer first cites them. */
  citations: Citation[];
  summary: AnswerSummary | undefined;
  trace: TraceSummary | undefined;
};

// "[3]" not already followed by "(": a link's text would be followed by its URL.
const MARKER = /( ?)\[(\d+)\](?!\()/g;

/** Verified markers become links the renderer turns into citation buttons. An unverified
 * citation is dropped, never shown in a weaker style (CitationMarker spec), so its marker goes
 * with the space before it. */
export function linkMarkers(text: string, verified: ReadonlySet<number>): string {
  return text.replace(MARKER, (_, space: string, n: string) =>
    verified.has(Number(n)) ? `${space}[${n}](#source-${n})` : "",
  );
}

/** The number a #source-n link points to, or null for any other URL. */
export function sourceNumber(href: string | undefined): number | null {
  const match = /^#source-(\d+)$/.exec(href ?? "");
  return match ? Number(match[1]) : null;
}

export function answerView(message: PlumblineMessage): AnswerView {
  const text = messageText(message);
  const byNumber = new Map<number, Citation>();
  for (const citation of dataParts(message, "citation")) {
    if (citation.verified) byNumber.set(citation.n, citation);
  }
  const firstCited = (n: number) => {
    const at = text.indexOf(`[${n}]`);
    return at === -1 ? Number.MAX_SAFE_INTEGER : at;
  };
  const citations = [...byNumber.values()].sort(
    (a, b) => firstCited(a.n) - firstCited(b.n) || a.n - b.n,
  );
  return {
    markdown: linkMarkers(text, new Set(byNumber.keys())),
    citations,
    summary: dataParts(message, "answer").at(-1),
    trace: dataParts(message, "trace").at(-1),
  };
}
