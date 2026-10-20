"use client";

import type { Jurisdiction } from "@plumbline/ts-client";
import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useRef, useState } from "react";

import { AnswerSkeleton } from "@/components/answer/answer-skeleton";
import type { AskValues } from "@/lib/ask-form";
import { prefetchAnswerChunks } from "@/lib/prefetch";
import { usageQuery, usageView } from "@/lib/usage";

import type { EngineControls, EngineState } from "./chat-engine";
import { ChatProfiler } from "./chat-profiler";
import { Composer } from "./composer";
import { EmptyState } from "./empty-state";

// Loaded on first use: the prefetch starts it when the question is focused, so by the time a
// question is sent it has usually arrived. Until it mounts, the first question waits under a
// skeleton. `ssr: false` keeps its scripts out of the page's HTML.
const ChatEngine = dynamic(() => import("./chat-engine").then((module) => module.ChatEngine), {
  ssr: false,
  loading: () => <AnswerSkeleton />,
});

/** The chat page: the empty state and the composer, which need nothing heavy, and the engine
 * that answers, which joins them when the first question is asked. One composer serves both,
 * so nothing typed or chosen has to move from one to another. */
export function Chat() {
  // The question that started the engine; null until then.
  const [first, setFirst] = useState<AskValues | null>(null);
  const controlsRef = useRef<EngineControls | null>(null);
  // The engine's state as the composer needs it; null until the engine has mounted.
  const [engine, setEngine] = useState<EngineState | null>(null);
  // The day's allowance: read again after each answer, and when none is left the composer says
  // so and when it resets before a question is typed.
  const { data: usage, dataUpdatedAt } = useQuery(usageQuery());
  const spent = usage ? usageView(usage, new Date(dataUpdatedAt)) : undefined;

  function ask(values: AskValues) {
    prefetchAnswerChunks();
    if (controlsRef.current) controlsRef.current.ask(values);
    else setFirst(values);
  }

  function askExample(question: string, jurisdiction: Jurisdiction) {
    ask({ question, jurisdictions: [jurisdiction], asOf: "" });
  }

  return (
    <ChatProfiler>
      <div className="mt-8 flex flex-col gap-8">
        {first === null ? (
          <EmptyState onExample={askExample} />
        ) : (
          <ChatEngine first={first} controlsRef={controlsRef} onState={setEngine} />
        )}
        <div className="sticky bottom-0 bg-bg pb-4 pt-2">
          <Composer
            // Busy from the first question until the engine says otherwise.
            busy={first !== null && (engine?.busy ?? true)}
            onAsk={ask}
            onStop={() => controlsRef.current?.stop()}
            disabledReason={
              engine?.quotaReason ?? (spent?.exhausted ? spent.composerReason : undefined)
            }
          />
        </div>
      </div>
    </ChatProfiler>
  );
}
