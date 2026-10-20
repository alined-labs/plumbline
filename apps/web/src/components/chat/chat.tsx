"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useState, type FormEvent } from "react";

import { Answer } from "@/components/answer/answer";
import { apiUrl } from "@/lib/api";
import { messageText, type PlumblineMessage } from "@/lib/messages";

const STAGE_LABELS: Record<string, string> = {
  detecting: "Finding the jurisdiction…",
  retrieving: "Searching the statutes…",
  reranking: "Ranking the passages…",
  generating: "Writing the answer…",
  verifying: "Checking every citation…",
};

export function Chat() {
  const [input, setInput] = useState("");
  const [stage, setStage] = useState<string | null>(null);
  const { messages, sendMessage, status, error } = useChat<PlumblineMessage>({
    transport: new DefaultChatTransport({ api: apiUrl("/api/ask") }),
    onData: (part) => {
      if (part.type === "data-status") setStage(part.data.stage);
    },
    onFinish: () => setStage(null),
  });
  const busy = status === "submitted" || status === "streaming";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    void sendMessage({ text });
    setInput("");
  }

  return (
    <div className="mt-8">
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <input
          id="question"
          name="question"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Can my landlord keep my deposit for cleaning?"
          maxLength={2000}
          className="min-h-11 flex-1 rounded-md border border-border-control bg-bg px-3 text-input"
        />
        <button
          type="submit"
          disabled={busy}
          className="min-h-11 rounded-md bg-accent px-4 font-medium text-accent-fg disabled:opacity-60"
        >
          Ask
        </button>
      </form>
      <p aria-live="polite" className="mt-3 min-h-6 text-small text-fg-muted">
        {busy ? (stage ? STAGE_LABELS[stage] : "Sending…") : ""}
      </p>
      {error && (
        <p role="alert" className="mt-3 text-small text-danger">
          The answer could not be completed. Try again in a moment.
        </p>
      )}
      <section aria-label="Conversation" role="log" className="mt-8 flex flex-col gap-8">
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
    </div>
  );
}
