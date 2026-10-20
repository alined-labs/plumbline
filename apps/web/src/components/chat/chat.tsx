"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useRef, useState } from "react";

import { Answer } from "@/components/answer/answer";
import { AnswerSkeleton } from "@/components/answer/answer-skeleton";
import { StatusSteps } from "@/components/answer/status-steps";
import { announcement, answerView } from "@/lib/answer";
import { apiUrl } from "@/lib/api";
import { askBody, type AskValues } from "@/lib/ask-form";
import { messageText, type PlumblineMessage } from "@/lib/messages";
import { addStatus, finishRun, startRun, type Run } from "@/lib/run";

import { Composer } from "./composer";

export function Chat() {
  // Status parts are transient: the chat keeps each request's steps itself, the live one
  // here and the finished ones by message id. The ref lets the stream's callbacks read it.
  const live = useRef<Run | null>(null);
  const [liveRun, setLiveRun] = useState<Run | null>(null);
  const [runs, setRuns] = useState<Record<string, Run>>({});
  const [announced, setAnnounced] = useState("");

  function setLive(run: Run | null) {
    live.current = run;
    setLiveRun(run);
  }

  const { messages, sendMessage, stop, status, error } = useChat<PlumblineMessage>({
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
      // One announcement per answer, once it is complete, instead of every token.
      setAnnounced(
        isError
          ? "The answer could not be completed."
          : isAbort
            ? "Answer stopped."
            : announcement(answerView(message)),
      );
    },
  });
  const busy = status === "submitted" || status === "streaming";
  const last = messages.at(-1);

  function ask(values: AskValues) {
    setLive(startRun(Date.now(), values.jurisdictions.length || 4));
    // The jurisdictions and as-of date travel in the body, beside the messages useChat sends.
    void sendMessage({ text: values.question }, { body: askBody(values) });
  }

  return (
    <div className="mt-8 flex flex-col gap-8">
      <section aria-label="Conversation" className="flex flex-col gap-8 empty:hidden">
        {messages.map((message) =>
          message.role === "assistant" ? (
            <Answer
              key={message.id}
              message={message}
              streaming={busy && message === last}
              run={busy && message === last ? (liveRun ?? undefined) : runs[message.id]}
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
      </section>
      <p aria-live="polite" className="sr-only">
        {announced}
      </p>
      {error && (
        <p role="alert" className="text-small text-danger">
          The answer could not be completed. Try again in a moment.
        </p>
      )}
      <div className="sticky bottom-0 bg-bg pb-4 pt-2">
        <Composer busy={busy} onAsk={ask} onStop={() => void stop()} />
      </div>
    </div>
  );
}
