"use client";

import { useEffect, useId, useRef, useState } from "react";

import { ThumbsDownIcon, ThumbsUpIcon } from "@/components/icons";
import { buttonClass } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Chip } from "@/components/ui/chip";
import { controlClass } from "@/components/ui/field";
import { Tip } from "@/components/ui/tip";
import { api, WITH_COOKIE } from "@/lib/api";
import {
  FEEDBACK_REASONS,
  feedbackBody,
  MAX_NOTE,
  type FeedbackReason,
  type FeedbackRequest,
} from "@/lib/feedback";

type Stage = "idle" | "asking" | "sent";
type Verdict = "helpful" | "not-helpful";

export type FeedbackState = ReturnType<typeof useFeedback>;

/** What a reader has said about one answer, and the call that carries it to the API. A thumbs
 * up is sent at once; a thumbs down opens the panel and is sent with its reasons. */
export function useFeedback(requestId: string) {
  const [stage, setStage] = useState<Stage>("idle");
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState(false);

  async function send(body: FeedbackRequest, as: Verdict) {
    setSending(true);
    setFailed(false);
    try {
      const { response } = await api.POST("/api/feedback", { body, ...WITH_COOKIE });
      if (!response.ok) throw new Error(`/api/feedback answered ${response.status}`);
      setVerdict(as);
      setStage("sent");
    } catch {
      setFailed(true);
    } finally {
      setSending(false);
    }
  }

  return {
    stage,
    verdict,
    sending,
    failed,
    helpful: () => void send(feedbackBody(requestId, { helpful: true }), "helpful"),
    notHelpful: () => {
      setVerdict("not-helpful");
      setStage("asking");
      setFailed(false);
    },
    cancel: () => {
      setVerdict(null);
      setStage("idle");
      setFailed(false);
    },
    sendReasons: (reasons: ReadonlySet<FeedbackReason>, note: string) =>
      void send(feedbackBody(requestId, { helpful: false, reasons, note }), "not-helpful"),
  };
}

const THUMB = "aria-pressed:bg-bg-active aria-pressed:text-fg";

/** Feedback spec, the buttons: Helpful and Not helpful as ghost icon buttons beside Copy.
 * Once the verdict is sent they stay as it was and a line thanks the reader. */
export function FeedbackButtons({
  feedback,
  panelId,
}: {
  feedback: FeedbackState;
  panelId: string;
}) {
  const sent = feedback.stage === "sent";
  return (
    <>
      <Tip label="Helpful">
        <button
          type="button"
          aria-label="Helpful"
          aria-pressed={feedback.verdict === "helpful"}
          disabled={sent || feedback.sending}
          onClick={feedback.helpful}
          className={buttonClass({ variant: "ghost", size: "sm", icon: true, className: THUMB })}
        >
          <ThumbsUpIcon />
        </button>
      </Tip>
      <Tip label="Not helpful">
        <button
          type="button"
          aria-label="Not helpful"
          aria-pressed={feedback.verdict === "not-helpful"}
          aria-expanded={feedback.stage === "asking"}
          aria-controls={panelId}
          disabled={sent}
          onClick={feedback.notHelpful}
          className={buttonClass({ variant: "ghost", size: "sm", icon: true, className: THUMB })}
        >
          <ThumbsDownIcon />
        </button>
      </Tip>
      <p role="status" className={sent ? "px-2 text-small text-fg-muted" : "sr-only"}>
        {sent ? "Thanks, that helps." : ""}
      </p>
    </>
  );
}

/** Feedback spec, the panel after Not helpful: "What went wrong?", the five reasons as chips
 * that can be combined, an optional note, Cancel and Send. */
export function FeedbackPanel({ feedback, id }: { feedback: FeedbackState; id: string }) {
  return <div id={id}>{feedback.stage === "asking" && <FeedbackForm feedback={feedback} />}</div>;
}

function FeedbackForm({ feedback }: { feedback: FeedbackState }) {
  const titleId = useId();
  const noteId = useId();
  const first = useRef<HTMLButtonElement>(null);
  const [reasons, setReasons] = useState<ReadonlySet<FeedbackReason>>(new Set());
  const [note, setNote] = useState("");

  // The panel opens under the button that was pressed; keyboard focus follows it in.
  useEffect(() => {
    first.current?.focus();
  }, []);

  function toggle(reason: FeedbackReason) {
    const next = new Set(reasons);
    if (!next.delete(reason)) next.add(reason);
    setReasons(next);
  }

  return (
    <div
      role="group"
      aria-labelledby={titleId}
      className="flex flex-col gap-2.5 rounded-lg border border-border bg-surface px-4 py-3.5"
    >
      <span id={titleId} className="text-ui-strong">
        What went wrong?
      </span>
      <div className="flex flex-wrap gap-1.5">
        {FEEDBACK_REASONS.map(({ id, label }, index) => (
          <Chip
            key={id}
            ref={index === 0 ? first : undefined}
            pressed={reasons.has(id)}
            onClick={() => toggle(id)}
          >
            {label}
          </Chip>
        ))}
      </div>
      <label htmlFor={noteId} className="sr-only">
        Note
      </label>
      <input
        id={noteId}
        value={note}
        maxLength={MAX_NOTE}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Anything else? (optional)"
        className={controlClass}
      />
      <p className="text-small text-fg-muted">Please leave out names and other personal details.</p>
      {feedback.failed && (
        <Callout tone="danger" title="Feedback didn't send.">
          Try again in a moment.
        </Callout>
      )}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={feedback.cancel}
          className={buttonClass({ variant: "ghost", size: "sm" })}
        >
          Cancel
        </button>
        <button
          type="button"
          disabled={feedback.sending}
          onClick={() => feedback.sendReasons(reasons, note)}
          className={buttonClass({ variant: "primary", size: "sm" })}
        >
          Send
        </button>
      </div>
    </div>
  );
}
