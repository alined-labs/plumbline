"use client";

import { useMemo, useState } from "react";

import { CircleCheckIcon } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { answerView, type AnswerView } from "@/lib/answer";
import type { PlumblineMessage } from "@/lib/messages";

import { Abstention, AnswerGap } from "./abstention";
import { AnswerBody } from "./answer-body";
import { SourceCard } from "./source-card";

/** Answer spec: the meta line, Plumbline's explanation with a marker after every claim, and
 * the sources it cites. A marker selects its source card, which is focused and outlined. */
export function Answer({ message }: { message: PlumblineMessage }) {
  const view = useMemo(() => answerView(message), [message]);
  const [selected, setSelected] = useState<number | null>(null);
  const sourceId = (n: number) => `source-${message.id}-${n}`;

  function select(n: number) {
    setSelected(n);
    document.getElementById(sourceId(n))?.focus();
  }

  return (
    <article aria-label="Answer" className="flex flex-col gap-4">
      <AnswerMeta view={view} />
      {view.summary?.status === "abstained" ? (
        <Abstention summary={view.summary} />
      ) : (
        <AnswerBody markdown={view.markdown} citations={view.citations} onSelect={select} />
      )}
      {view.summary?.status === "partial" && <AnswerGap reason={view.summary.abstain_reason} />}
      {view.summary?.status !== "abstained" && view.citations.length > 0 && (
        <ol
          aria-label="Sources"
          className="grid grid-cols-[repeat(auto-fill,minmax(--spacing(65),1fr))] gap-2"
        >
          {view.citations.map((citation) => (
            <SourceCard
              key={citation.n}
              id={sourceId(citation.n)}
              citation={citation}
              selected={selected === citation.n}
            />
          ))}
        </ol>
      )}
    </article>
  );
}

/** "Partial answer · 1 source verified · stub · full tier": the answer's status when it is
 * not a plain answer, what was verified, and the model-and-tier badge from the trace. Shown
 * once the answer is complete. */
function AnswerMeta({ view }: { view: AnswerView }) {
  const { citations, summary, trace } = view;
  if (!summary) return null;
  const count = citations.length;
  return (
    <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-small text-fg-muted">
      {summary.status === "partial" && <Badge tone="warning">Partial answer</Badge>}
      {summary.status === "abstained" && <Badge tone="neutral">Abstained</Badge>}{" "}
      {summary.status !== "abstained" && count > 0 && (
        <span className="inline-flex items-center gap-1 font-medium text-success">
          <CircleCheckIcon size={14} strokeWidth={2} />
          {count} {count === 1 ? "source" : "sources"} verified
        </span>
      )}{" "}
      {trace && (
        <span className="inline-flex items-center gap-1.5 rounded-sm border border-border px-1.5">
          <span className="font-mono text-code-sm">{trace.model}</span>
          {" · "}
          {trace.tier} tier{trace.cached && " · replayed"}
        </span>
      )}
    </p>
  );
}
