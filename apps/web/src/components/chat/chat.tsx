"use client";

import { useChat } from "@ai-sdk/react";
import type { Jurisdiction } from "@plumbline/ts-client";
import { APICallError, DefaultChatTransport } from "ai";
import { useRef, useState } from "react";

import { Answer } from "@/components/answer/answer";
import { AnswerSkeleton } from "@/components/answer/answer-skeleton";
import { StatusSteps } from "@/components/answer/status-steps";
import { RotateCwIcon } from "@/components/icons";
import { buttonClass } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { announcement, answerView } from "@/lib/answer";
import { apiUrl } from "@/lib/api";
import { askBody, type AskBody, type AskValues } from "@/lib/ask-form";
import { untilUtcMidnight } from "@/lib/dates";
import { messageText, type PlumblineMessage } from "@/lib/messages";
import { addStatus, finishRun, startRun, type Run } from "@/lib/run";

import { Composer } from "./composer";
import { EmptyState } from "./empty-state";

/** Over the demo's daily quota, the API answers 429 (Patterns to rebuild: sandbox quotas). */
function isQuotaReached(error: unknown): boolean {
  return APICallError.isInstance(error) && error.statusCode === 429;
}

export function Chat() {
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

  function setLive(run: Run | null) {
    live.current = run;
    setLiveRun(run);
  }

  const { messages, sendMessage, regenerate, stop, status, error } = useChat<PlumblineMessage>({
    transport: new DefaultChatTransport({ api: apiUrl("/api/ask") }),
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
    },
    onError: (failure) => {
      if (isQuotaReached(failure)) setResetIn(untilUtcMidnight(new Date()));
    },
  });
  const busy = status === "submitted" || status === "streaming";
  const last = messages.at(-1);

  function ask(values: AskValues) {
    lastBody.current = askBody(values);
    setLive(startRun(Date.now(), values.jurisdictions.length || 4));
    // The jurisdictions and as-of date travel in the body, beside the messages useChat sends.
    void sendMessage({ text: values.question }, { body: lastBody.current });
  }

  function askExample(question: string, jurisdiction: Jurisdiction) {
    ask({ question, jurisdictions: [jurisdiction], asOf: "" });
  }

  function retry() {
    setLive(startRun(Date.now(), lastBody.current.jurisdictions.length || 4));
    void regenerate({ body: lastBody.current });
  }

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
        {"The search service didn't answer. Your question is kept; try again in a moment."}
      </Callout>
    );

  return (
    <div className="mt-8 flex flex-col gap-8">
      {messages.length === 0 && <EmptyState onExample={askExample} />}
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
      <div className="sticky bottom-0 bg-bg pb-4 pt-2">
        <Composer
          busy={busy}
          onAsk={ask}
          onStop={() => void stop()}
          disabledReason={
            isQuotaReached(error)
              ? `Demo questions reset at 00:00 UTC${resetIn ? `, in ${resetIn}` : ""}.`
              : undefined
          }
        />
      </div>
    </div>
  );
}
