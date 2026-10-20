"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { Answer } from "@/components/answer/answer";
import { AnswerSkeleton } from "@/components/answer/answer-skeleton";
import { ChevronLeftIcon } from "@/components/icons";
import { CodeBadge } from "@/components/ui/badge";
import { buttonClass } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { JURISDICTIONS } from "@/lib/jurisdictions";
import { messageText } from "@/lib/messages";
import { toMessages, type ReplayFile, type ReplayItem } from "@/lib/replay";

// The static tier's chat: the live demo is paused, and the reader reads the answers Plumbline
// recorded for the benchmark's development questions instead, in the same answer view.

async function fetchReplay(): Promise<ReplayFile> {
  const response = await fetch("/replay.json");
  if (!response.ok) throw new Error(`/replay.json answered ${response.status}`);
  return (await response.json()) as ReplayFile;
}

/** The recorded questions by jurisdiction in the fixed order, then the rest under one heading. */
function groups(items: ReplayItem[]) {
  const single = JURISDICTIONS.map((jurisdiction) => ({
    key: jurisdiction.id,
    code: jurisdiction.code,
    name: jurisdiction.name,
    items: items.filter(
      (item) => item.jurisdictions.length === 1 && item.jurisdictions[0] === jurisdiction.id,
    ),
  }));
  const other = {
    key: "other",
    code: null,
    name: "Across jurisdictions, or outside them",
    items: items.filter((item) => item.jurisdictions.length !== 1),
  };
  return [...single, other].filter((group) => group.items.length > 0);
}

export function Replay() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["replay"],
    queryFn: fetchReplay,
    staleTime: Infinity,
    retry: false,
  });
  const [chosen, setChosen] = useState<ReplayItem | null>(null);
  // The question last read, to put the focus back on it in the list.
  const back = useRef<string | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const answerHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (chosen) answerHeading.current?.focus();
    else if (back.current) {
      list.current?.querySelector<HTMLButtonElement>(`[data-item="${back.current}"]`)?.focus();
    }
  }, [chosen]);

  const notice = (
    <Callout tone="info" title="The live demo is paused.">
      {data?.config
        ? `These are the answers Plumbline recorded for the benchmark's development questions with its ${data.config} configuration, checked the same way as live ones.`
        : "Its recorded answers are not published yet; the evaluation and the statutes' dates stay open."}
    </Callout>
  );

  if (isPending) return <AnswerSkeleton />;
  if (isError || !data.config || data.items.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        {isError ? (
          <Callout tone="info" title="The live demo is paused.">
            Its recorded answers could not be loaded; the evaluation and the statutes&apos; dates
            stay open.
          </Callout>
        ) : (
          notice
        )}
      </div>
    );
  }

  if (chosen) {
    const config = data.config;
    const [question, answer] = toMessages(chosen, config, data.config_hash ?? "");
    return (
      <div className="flex flex-col gap-6">
        {notice}
        <h2 ref={answerHeading} tabIndex={-1} className="sr-only">
          Recorded answer
        </h2>
        <section aria-label="Conversation" className="flex flex-col gap-8">
          {question && (
            <p className="max-w-4/5 self-end rounded-lg bg-bg-active px-3.5 py-2.5 text-body">
              {messageText(question)}
            </p>
          )}
          {answer && <Answer message={answer} />}
        </section>
        <div>
          <button
            type="button"
            onClick={() => {
              back.current = chosen.item_id;
              setChosen(null);
            }}
            className={buttonClass()}
          >
            <ChevronLeftIcon />
            Another question
          </button>
        </div>
      </div>
    );
  }

  return (
    <div ref={list} className="flex flex-col gap-6">
      {notice}
      <h2 className="text-heading-2">Recorded questions</h2>
      {groups(data.items).map((group) => (
        <section
          key={group.key}
          aria-labelledby={`replay-${group.key}`}
          className="flex flex-col gap-2"
        >
          <h3 id={`replay-${group.key}`} className="flex items-center gap-2 text-heading-3">
            {group.code && <CodeBadge code={group.code} />}
            {group.name}
          </h3>
          <ul className="flex flex-col divide-y divide-border-subtle rounded-lg border border-border">
            {group.items.map((item) => (
              <li key={item.item_id}>
                <button
                  type="button"
                  data-item={item.item_id}
                  onClick={() => setChosen(item)}
                  className="w-full px-3.5 py-2.5 text-left text-ui text-fg hover:bg-bg-hover max-md:min-h-11"
                >
                  {item.question}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
