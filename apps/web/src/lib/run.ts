import type { StatusEvent } from "@plumbline/ts-client";

// One request's progress, from the transient data-status parts. The parts carry no times,
// so the browser stamps each one as it arrives.

export type Stage = StatusEvent["stage"];

export type Step = {
  stage: Stage;
  detail: string | null;
  startedAt: number;
  endedAt: number | null;
  failed: boolean;
};

export type Run = {
  startedAt: number;
  finishedAt: number | null;
  /** How many jurisdictions the question searches: its filter, or all four. */
  scope: number;
  steps: Step[];
};

export function startRun(now: number, scope: number): Run {
  return { startedAt: now, finishedAt: null, scope, steps: [] };
}

function closeLast(steps: Step[], now: number, failed = false): Step[] {
  const last = steps.at(-1);
  if (!last || last.endedAt !== null) return steps;
  return [...steps.slice(0, -1), { ...last, endedAt: now, failed }];
}

/** A new stage ends the one before it; the same stage again only updates its detail. */
export function addStatus(run: Run, { stage, detail }: StatusEvent, now: number): Run {
  const last = run.steps.at(-1);
  if (last && last.stage === stage && last.endedAt === null) {
    return {
      ...run,
      steps: [...run.steps.slice(0, -1), { ...last, detail: detail ?? last.detail }],
    };
  }
  const step: Step = {
    stage,
    detail: detail ?? null,
    startedAt: now,
    endedAt: null,
    failed: false,
  };
  return { ...run, steps: [...closeLast(run.steps, now), step] };
}

export function finishRun(run: Run, now: number, failed = false): Run {
  return { ...run, finishedAt: now, steps: closeLast(run.steps, now, failed) };
}

/** StatusSteps spec: the stage names, in the reader's terms. */
export function stepLabel(stage: Stage, scope: number): string {
  switch (stage) {
    case "detecting":
      return "Reading your question";
    case "retrieving":
      return `Searching ${scope} ${scope === 1 ? "jurisdiction" : "jurisdictions"}`;
    case "reranking":
      return "Ranking passages";
    case "generating":
      return "Writing the answer";
    case "verifying":
      return "Checking citations";
  }
}

/** "4.2 s", the way the content rules write durations. */
export function seconds(ms: number): string {
  return `${(Math.max(0, ms) / 1000).toFixed(1)} s`;
}
