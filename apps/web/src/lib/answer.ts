import type { AnswerSummary, Citation, TraceSummary } from "@plumbline/ts-client";

import { DISCLAIMER } from "./copy";
import { dataParts, messageText, type PlumblineMessage } from "./messages";
import { isWithheld } from "./replay";

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

/** What the live region says once an answer is complete: the whole answer in plain words,
 * read once, instead of every token as it streams. */
export function announcement({ markdown, citations, summary }: AnswerView): string {
  if (summary?.status === "abstained") {
    return ["I couldn't find a statute that answers this.", summary.abstain_reason ?? ""]
      .join(" ")
      .trim();
  }
  const words = markdown
    .replace(/ ?\[\d+\]\(#source-\d+\)/g, "")
    .replace(/[*_`#>]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  const count = citations.length;
  const sources = `${count} ${count === 1 ? "source" : "sources"} verified.`;
  return summary?.status === "partial"
    ? `Partial answer: ${words} ${sources} Part of the question isn't covered by the statutes I hold.`
    : `Answer: ${words} ${sources}`;
}

/** An answer as plain text for the clipboard: Plumbline's words with their [n] markers, the
 * sources they cite in the law's own words, and the disclaimer, so a pasted answer keeps its
 * evidence and its framing. */
export function answerAsText({ markdown, citations, summary }: AnswerView): string {
  const disclaimer = summary?.disclaimer ?? DISCLAIMER;
  if (summary?.status === "abstained") {
    const reason = summary.abstain_reason ? ` ${summary.abstain_reason}` : "";
    return `I couldn't find a statute that answers this.${reason}\n\n${disclaimer}`;
  }
  const words = markdown.replace(/\[(\d+)\]\(#source-\d+\)/g, "[$1]").trim();
  const sources = citations.map(({ n, label, quote, gloss }) =>
    isWithheld(quote)
      ? `[${n}] ${label} (passage not republished here; see the official text)`
      : `[${n}] ${label}: "${quote}"${gloss ? ` (${gloss})` : ""}`,
  );
  const gap =
    summary?.status === "partial"
      ? `\n\nNot covered by the statutes I hold: ${summary.abstain_reason ?? "part of this question."}`
      : "";
  return [words + gap, sources.length ? `Sources\n${sources.join("\n")}` : "", disclaimer]
    .filter(Boolean)
    .join("\n\n");
}
