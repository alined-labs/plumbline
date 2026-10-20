"use client";

import { Fragment, useId, useMemo, useState, type ReactNode } from "react";

import { CheckIcon, CircleCheckIcon, CopyIcon } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { buttonClass } from "@/components/ui/button";
import { Tip } from "@/components/ui/tip";
import { answerAsText, answerView, type AnswerView } from "@/lib/answer";
import type { PlumblineMessage } from "@/lib/messages";
import { seconds, type Run } from "@/lib/run";

import { Abstention, AnswerGap } from "./abstention";
import { AnswerBody } from "./answer-body";
import { AnswerSkeleton } from "./answer-skeleton";
import { FeedbackButtons, FeedbackPanel, useFeedback } from "./feedback";
import { usePanel } from "./panel-context";
import { SourceCard } from "./source-card";
import { StatusSteps } from "./status-steps";

/** Answer spec: the meta line (the status steps while it streams), Plumbline's explanation with
 * a marker after every claim, and the sources it cites. A marker or a source card opens its
 * passage in the source panel, and focus returns to it when the panel closes. */
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
  const panel = usePanel();
  // The source open in the panel, if it is one of this answer's.
  const open = panel.subject?.messageId === message.id ? panel.subject.n : null;
  const status = view.summary?.status;

  function openPanel(n: number | null, tab: "sources" | "trace", from: HTMLElement) {
    panel.open(
      { messageId: message.id, citations: view.citations, n, tab, trace: view.trace, run },
      from,
    );
  }
  const openSource = (n: number, from: HTMLElement) => openPanel(n, "sources", from);

  return (
    <article aria-label="Answer" aria-busy={streaming || undefined} className="flex flex-col gap-4">
      {streaming ? (
        run && run.steps.length > 0 ? (
          <StatusSteps run={run} />
        ) : (
          <AnswerSkeleton />
        )
      ) : (
        <AnswerMeta view={view} run={run} onTrace={(from) => openPanel(null, "trace", from)} />
      )}
      {failure ?? (
        <>
          {view.summary?.status === "abstained" ? (
            <Abstention summary={view.summary} />
          ) : (
            view.markdown && (
              <AnswerBody
                markdown={view.markdown}
                citations={view.citations}
                active={open}
                onOpen={openSource}
              />
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
                  citation={citation}
                  selected={open === citation.n}
                  onOpen={openSource}
                />
              ))}
            </ol>
          )}
        </>
      )}
      {!streaming && !failure && view.summary && <AnswerActions view={view} />}
    </article>
  );
}

/** "Partial answer · 1 source verified · Answered in 4.2 s · stub · full tier · Trace": the
 * status when it is not a plain answer, what was verified, how long it took, the
 * model-and-tier badge from the trace, and the trace itself one click away, in the panel. */
function AnswerMeta({
  view,
  run,
  onTrace,
}: {
  view: AnswerView;
  run: Run | undefined;
  onTrace: (opener: HTMLElement) => void;
}) {
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
    (trace || (run && run.steps.length > 0)) && (
      <button
        type="button"
        aria-haspopup="dialog"
        onClick={(event) => onTrace(event.currentTarget)}
        className="rounded-xs text-accent underline underline-offset-2 hover:text-accent-hover"
      >
        Trace
      </button>
    ),
  ].filter(Boolean);

  return (
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
  );
}

/** Answer spec, actions: copy the answer with its sources and the disclaimer, and say whether it
 * helped. A "not helpful" opens the reasons under the row. */
function AnswerActions({ view }: { view: AnswerView }) {
  const [copied, setCopied] = useState(false);
  const requestId = view.trace?.request_id;
  const feedback = useFeedback(requestId ?? "");
  const panelId = useId();

  async function copy() {
    try {
      await navigator.clipboard.writeText(answerAsText(view));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // The browser refused the clipboard; the answer is still on the page to select.
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-0.5">
        <Tip label={copied ? "Copied" : "Copy answer"}>
          <button
            type="button"
            onClick={copy}
            aria-label={copied ? "Answer copied" : "Copy answer"}
            className={buttonClass({ variant: "ghost", size: "sm", icon: true })}
          >
            {copied ? <CheckIcon /> : <CopyIcon />}
          </button>
        </Tip>
        {/* An answer with no trace has no request to attach a verdict to. */}
        {requestId && <FeedbackButtons feedback={feedback} panelId={panelId} />}
        <p aria-live="polite" className="sr-only">
          {copied ? "Answer copied with its sources" : ""}
        </p>
      </div>
      {requestId && <FeedbackPanel feedback={feedback} id={panelId} />}
    </div>
  );
}
