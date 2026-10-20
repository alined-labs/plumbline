"use client";

import { useChat } from "@ai-sdk/react";
import { useQueryClient } from "@tanstack/react-query";
import { APICallError, DefaultChatTransport } from "ai";
import { useEffect, useRef, useState, type RefObject } from "react";

import { Answer } from "@/components/answer/answer";
import { AnswerSkeleton } from "@/components/answer/answer-skeleton";
import { StatusSteps } from "@/components/answer/status-steps";
import { RotateCwIcon } from "@/components/icons";
import { buttonClass } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { announcement, answerView } from "@/lib/answer";
import { apiUrl, WITH_COOKIE } from "@/lib/api";
import { askBody, type AskBody, type AskValues } from "@/lib/ask-form";
import { untilUtcMidnight } from "@/lib/dates";
import { messageText, type PlumblineMessage } from "@/lib/messages";
import { addStatus, finishRun, startRun, type Run } from "@/lib/run";

// The chat's engine: the AI SDK's useChat, its transport and the conversation it streams. It is
// a chunk of its own, loaded when the reader first focuses the question or asks one, so the
// page's first load carries only the shell and the composer (docs/notes/mobile-performance.md).

/** What the shell's composer needs from the engine. */
export type EngineState = {
  busy: boolean;
  /** Set when the API answered 429: the composer's words until the quota resets. */
  quotaReason: string | null;
};

/** How the shell's composer drives the engine once it has loaded. */
export type EngineControls = { ask: (values: AskValues) => void; stop: () => void };

/** Over the demo's daily quota, the API answers 429 (Patterns to rebuild: sandbox quotas). */
function isQuotaReached(error: unknown): boolean {
  return APICallError.isInstance(error) && error.statusCode === 429;
}

export function ChatEngine({
  first,
  controlsRef,
  onState,
  onReplay,
}: {
  /** The question that loaded the engine, asked as soon as it mounts. */
  first: AskValues;
  controlsRef: RefObject<EngineControls | null>;
  onState: (state: EngineState) => void;
  /** Offered when the API did not answer: the static tier's recorded answers instead. */
  onReplay: () => void;
}) {
  // Status parts are transient: the chat keeps each request's steps itself, the live one
  // here and the finished ones by message id. The ref lets the stream's callbacks read it.
  const live = useRef<Run | null>(null);
  const [liveRun, setLiveRun] = useState<Run | null>(null);
  const [runs, setRuns] = useState<Record<string, Run>>({});
  const [announced, setAnnounced] = useState("");
  // The time left until the quota resets, measured when the 429 arrives.
  const [resetIn, setResetIn] = useState<string | null>(null);
  // The filters of the last question, so Try again asks it the same way.
  const lastBody = useRef<AskBody>({ as_of: null, jurisdictions: [] });
  const queryClient = useQueryClient();

  function setLive(run: Run | null) {
    live.current = run;
    setLiveRun(run);
  }

  const { messages, sendMessage, regenerate, stop, status, error } = useChat<PlumblineMessage>({
    // The visitor cookie goes with each question, so the day's allowance counts the visitor.
    transport: new DefaultChatTransport({ api: apiUrl("/api/ask"), ...WITH_COOKIE }),
    // Publish streamed text at most every 50 ms: tokens arrive faster than that, and each
    // update re-renders the answer (docs/notes/streamed-answer-profile.md).
    throttle: 50,
    onData: (part) => {
      if (part.type === "data-status" && live.current) {
        setLive(addStatus(live.current, part.data, Date.now()));
      }
    },
    onFinish: ({ message, isError, isAbort }) => {
      const run = live.current;
      if (run) setRuns((all) => ({ ...all, [message.id]: finishRun(run, Date.now(), isError) }));
      setLive(null);
      // One announcement per answer, once it is complete, instead of every token. A failure
      // announces itself through its callout.
      setAnnounced(isError ? "" : isAbort ? "Answer stopped." : announcement(answerView(message)));
      void queryClient.invalidateQueries({ queryKey: ["usage"] });
    },
    onError: (failure) => {
      if (isQuotaReached(failure)) setResetIn(untilUtcMidnight(new Date()));
      void queryClient.invalidateQueries({ queryKey: ["usage"] });
    },
  });
  const busy = status === "submitted" || status === "streaming";
  const last = messages.at(-1);
  const quotaReason = isQuotaReached(error)
    ? `Demo questions reset at 00:00 UTC${resetIn ? `, in ${resetIn}` : ""}.`
    : null;

  function ask(values: AskValues) {
    lastBody.current = askBody(values);
    setLive(startRun(Date.now(), values.jurisdictions.length || 4));
    // The jurisdictions and as-of date travel in the body, beside the messages useChat sends.
    void sendMessage({ text: values.question }, { body: lastBody.current });
  }

  function retry() {
    setLive(startRun(Date.now(), lastBody.current.jurisdictions.length || 4));
    void regenerate({ body: lastBody.current });
  }

  // The shell's composer reaches the latest ask and stop through this ref.
  useEffect(() => {
    controlsRef.current = { ask, stop: () => void stop() };
  });
  useEffect(() => () => void (controlsRef.current = null), [controlsRef]);

  // The question that loaded the engine, asked once (Strict Mode mounts effects twice).
  const asked = useRef(false);
  useEffect(() => {
    if (asked.current) return;
    asked.current = true;
    ask(first);
    // Only on mount: later questions come through the controlsRef.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    onState({ busy, quotaReason });
  }, [busy, quotaReason, onState]);

  // ErrorState and Callout specs: an answer that failed shows a danger callout with Try
  // again; a spent quota is not a failure, so it says when the demo resets.
  const failure =
    status !== "error" ? undefined : isQuotaReached(error) ? (
      <Callout tone="warning" title="Today's demo questions are used up.">
        {`They reset at 00:00 UTC${resetIn ? `, in ${resetIn}` : ""}. `}
        {"The evaluation and the statutes' dates stay open."}
      </Callout>
    ) : (
      <Callout
        tone="danger"
        title="Plumbline couldn't finish this answer."
        action={
          <button type="button" onClick={retry} className={buttonClass({ size: "sm" })}>
            <RotateCwIcon />
            Try again
          </button>
        }
      >
        The search service didn&apos;t answer. Your question is kept; try again in a moment, or{" "}
        <button
          type="button"
          onClick={onReplay}
          className="text-accent underline underline-offset-2 hover:text-accent-hover"
        >
          read the answers Plumbline recorded
        </button>{" "}
        for the benchmark&apos;s questions.
      </Callout>
    );

  return (
    <>
      <section aria-label="Conversation" className="flex flex-col gap-8 empty:hidden">
        {messages.map((message) =>
          message.role === "assistant" ? (
            <Answer
              key={message.id}
              message={message}
              streaming={busy && message === last}
              run={busy && message === last ? (liveRun ?? undefined) : runs[message.id]}
              failure={message === last ? failure : undefined}
            />
          ) : (
            <p
              key={message.id}
              className="max-w-4/5 self-end rounded-lg bg-bg-active px-3.5 py-2.5 text-body"
            >
              {messageText(message)}
            </p>
          ),
        )}
        {busy && last?.role === "user" && (
          // Before the stream's first part there is no assistant message yet.
          <div className="flex flex-col gap-4">
            {liveRun && liveRun.steps.length > 0 ? (
              <StatusSteps run={liveRun} />
            ) : (
              <AnswerSkeleton />
            )}
          </div>
        )}
        {/* A request that failed before its answer began has no message to hold the callout. */}
        {last?.role === "user" && failure}
      </section>
      <p aria-live="polite" className="sr-only">
        {announced}
      </p>
    </>
  );
}
