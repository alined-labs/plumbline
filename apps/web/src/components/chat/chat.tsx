"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useState } from "react";

import { Answer } from "@/components/answer/answer";
import { apiUrl } from "@/lib/api";
import { askBody, type AskValues } from "@/lib/ask-form";
import { messageText, type PlumblineMessage } from "@/lib/messages";

import { Composer } from "./composer";

const STAGE_LABELS: Record<string, string> = {
  detecting: "Finding the jurisdiction…",
  retrieving: "Searching the statutes…",
  reranking: "Ranking the passages…",
  generating: "Writing the answer…",
  verifying: "Checking every citation…",
};

export function Chat() {
  const [stage, setStage] = useState<string | null>(null);
  const { messages, sendMessage, stop, status, error } = useChat<PlumblineMessage>({
    transport: new DefaultChatTransport({ api: apiUrl("/api/ask") }),
    onData: (part) => {
      if (part.type === "data-status") setStage(part.data.stage);
    },
    onFinish: () => setStage(null),
  });
  const busy = status === "submitted" || status === "streaming";

  function ask(values: AskValues) {
    // The jurisdictions and as-of date travel in the body, beside the messages useChat sends.
    void sendMessage({ text: values.question }, { body: askBody(values) });
  }

  return (
    <div className="mt-8 flex flex-col gap-8">
      <section aria-label="Conversation" role="log" className="flex flex-col gap-8 empty:hidden">
        {messages.map((message) =>
          message.role === "assistant" ? (
            <Answer key={message.id} message={message} />
          ) : (
            <p
              key={message.id}
              className="max-w-4/5 self-end rounded-lg bg-bg-active px-3.5 py-2.5 text-body"
            >
              {messageText(message)}
            </p>
          ),
        )}
      </section>
      <p aria-live="polite" className="min-h-6 text-small text-fg-muted empty:hidden">
        {busy ? (stage ? STAGE_LABELS[stage] : "Sending…") : ""}
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
