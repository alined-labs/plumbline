"use client";

import { Fragment, useId, useMemo, useState, type ReactNode } from "react";

import { CircleCheckIcon } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { answerView, type AnswerView } from "@/lib/answer";
import type { PlumblineMessage } from "@/lib/messages";
import { seconds, type Run } from "@/lib/run";

import { Abstention, AnswerGap } from "./abstention";
import { AnswerBody } from "./answer-body";
import { AnswerSkeleton } from "./answer-skeleton";
import { SourceCard } from "./source-card";
import { StatusSteps } from "./status-steps";

/** Answer spec: the meta line (the status steps while it streams), Plumbline's explanation with
 * a marker after every claim, and the sources it cites. A marker selects its source card,
 * which is focused and outlined. */
export function Answer({
  message,
  run,
  streaming = false,
  failure,
}: {
  message: PlumblineMessage;
  /** Shown in place of the body and sources when the answer could not be completed. */
  failure?: ReactNode;
  /** The request's progress, kept by the chat: the stream does not store it in the message. */
  run?: Run;
  streaming?: boolean;
}) {
  const view = useMemo(() => answerView(message), [message]);
  const [selected, setSelected] = useState<number | null>(null);
  const sourceId = (n: number) => `source-${message.id}-${n}`;
  const status = view.summary?.status;

  function select(n: number) {
    setSelected(n);
    document.getElementById(sourceId(n))?.focus();
  }

  return (
    <article aria-label="Answer" aria-busy={streaming || undefined} className="flex flex-col gap-4">
      {streaming ? (
        run && run.steps.length > 0 ? (
          <StatusSteps run={run} />
        ) : (
          <AnswerSkeleton />
        )
      ) : (
        <AnswerMeta view={view} run={run} />
      )}
      {failure ?? (
        <>
          {view.summary?.status === "abstained" ? (
            <Abstention summary={view.summary} />
          ) : (
            view.markdown && (
              <AnswerBody markdown={view.markdown} citations={view.citations} onSelect={select} />
            )
          )}
          {status === "partial" && <AnswerGap reason={view.summary?.abstain_reason ?? null} />}
          {status !== "abstained" && view.citations.length > 0 && (
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
        </>
      )}
    </article>
  );
}

/** "Partial answer · 1 source verified · Answered in 4.2 s · stub · full tier · Trace": the
 * status when it is not a plain answer, what was verified, how long it took, the
 * model-and-tier badge from the trace, and the status steps one click away. */
function AnswerMeta({ view, run }: { view: AnswerView; run: Run | undefined }) {
  const [open, setOpen] = useState(false);
  const stepsId = useId();
  const { citations, summary, trace } = view;
  if (!summary) return null;
  const count = citations.length;
  const items = [
    summary.status === "partial" && <Badge tone="warning">Partial answer</Badge>,
    summary.status === "abstained" && <Badge tone="neutral">Abstained</Badge>,
    summary.status !== "abstained" && count > 0 && (
      <span className="inline-flex items-center gap-1 font-medium text-success">
        <CircleCheckIcon size={14} strokeWidth={2} />
        {count} {count === 1 ? "source" : "sources"} verified
      </span>
    ),
    run && run.finishedAt !== null && (
      <span>Answered in {seconds(run.finishedAt - run.startedAt)}</span>
    ),
    trace && (
      <span className="inline-flex items-center gap-1.5 rounded-sm border border-border px-1.5">
        <span className="font-mono text-code-sm">{trace.model}</span>
        {" · "}
        {trace.tier} tier{trace.cached && " · replayed"}
      </span>
    ),
    run && run.steps.length > 0 && (
      <button
        type="button"
        aria-expanded={open}
        aria-controls={stepsId}
        onClick={() => setOpen(!open)}
        className="rounded-xs text-accent underline underline-offset-2 hover:text-accent-hover"
      >
        Trace
      </button>
    ),
  ].filter(Boolean);

  return (
    <div className="flex flex-col gap-2">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-small text-fg-muted">
        {items.map((item, i) => (
          <Fragment key={i}>
            {i > 0 && (
              <>
                {" "}
                <span aria-hidden="true" className="text-fg-subtle">
                  ·
                </span>{" "}
              </>
            )}
            {item}
          </Fragment>
        ))}
      </p>
      {run && open && (
        <div id={stepsId}>
          <StatusSteps run={run} />
        </div>
      )}
    </div>
  );
}
