"use client";

import type { Jurisdiction } from "@plumbline/ts-client";
import dynamic from "next/dynamic";
import { useRef, useState } from "react";

import { AnswerSkeleton } from "@/components/answer/answer-skeleton";
import type { AskValues } from "@/lib/ask-form";
import { prefetchAnswerChunks } from "@/lib/prefetch";
import { replayQuery } from "@/lib/replay";
import { useDemoMode } from "@/lib/tier";
import { usageView, useUsage } from "@/lib/usage";
import { useQuery } from "@tanstack/react-query";

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

// The static tier's replay of stored answers, loaded only when the page turns out to be one.
const Replay = dynamic(() => import("./replay").then((module) => module.Replay), {
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
  // Live until the API says otherwise; a question already asked keeps its conversation.
  const mode = useDemoMode();
  // The reader may also choose the recorded answers when a live question fails.
  const [replayChosen, setReplayChosen] = useState(false);
  const replay = (mode === "replay" && first === null) || replayChosen;
  // Whether the export holds recorded answers, read with the replay itself.
  const { data: recorded } = useQuery({ ...replayQuery(), enabled: replay });
  const hasRecorded = (recorded?.items.length ?? 0) > 0;
  const { data: usage, dataUpdatedAt } = useUsage();
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
        {replay ? (
          <Replay />
        ) : first === null ? (
          <EmptyState onExample={askExample} />
        ) : (
          <ChatEngine
            first={first}
            controlsRef={controlsRef}
            onState={setEngine}
            onReplay={() => setReplayChosen(true)}
          />
        )}
        {/* The composer stays in the replay too, so the page does not move under the reader. */}
        <div className="sticky bottom-0 bg-bg pb-4 pt-2">
          <Composer
            // Busy from the first question until the engine says otherwise.
            busy={!replay && first !== null && (engine?.busy ?? true)}
            onAsk={ask}
            onStop={() => controlsRef.current?.stop()}
            disabledReason={
              replay
                ? hasRecorded
                  ? "The live demo is paused: choose one of the recorded questions above."
                  : "The live demo is paused for now."
                : (engine?.quotaReason ?? (spent?.exhausted ? spent.composerReason : undefined))
            }
          />
        </div>
      </div>
    </ChatProfiler>
  );
}
