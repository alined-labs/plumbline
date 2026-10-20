import type { Finding } from "./lease";
import type { LeaseEvent, LeaseStage } from "./lease-check";

// The state of one lease check as the page needs it: a reducer over the start of the upload,
// the stream's events and a failure. It keeps what the page shows (the file's name and size,
// the stage, the clause counts, the findings) and not the file itself, which the page holds
// for Try again. It imports only types, so the provider that lives in every page's layout
// carries the reducer and none of the transport (the steps and the wording are in the files
// the lease page alone loads).

/** What the page needs of a failure: its code, the words to fall back on and any wait. A
 * LeaseFailure has all three, and so does the plain object made when the transport could not
 * even load. */
export type JobFailure = { code: string; message: string; retryAfter?: number };

/** What the page keeps of the file it sent. */
export type JobFile = { name: string; size: number };

type Run = {
  file: JobFile;
  /** The stage the checker last reported; null while the upload is still under way. */
  stage: LeaseStage | null;
  /** Clauses checked so far, once the checker counts them. */
  clauses: { done: number; total: number } | null;
  /** In the order they arrive, which is clause order. */
  findings: readonly Finding[];
};

export type LeaseJob =
  | { status: "idle" }
  | ({ status: "running" } & Run)
  | ({ status: "done"; language: "en" | "es" } & Run)
  | ({ status: "failed"; failure: JobFailure } & Run);

export type StartedJob = Exclude<LeaseJob, { status: "idle" }>;

export type JobAction =
  | { type: "start"; file: JobFile }
  | { type: "event"; event: LeaseEvent }
  | { type: "fail"; failure: JobFailure }
  | { type: "reset" };

export const IDLE: LeaseJob = { status: "idle" };

export function reduceJob(job: LeaseJob, action: JobAction): LeaseJob {
  switch (action.type) {
    case "start":
      return { status: "running", file: action.file, stage: null, clauses: null, findings: [] };
    case "reset":
      return IDLE;
    case "fail":
      return job.status === "running" ? { ...job, status: "failed", failure: action.failure } : job;
    case "event": {
      // An event that arrives after a cancel or a failure belongs to a check that is over.
      if (job.status !== "running") return job;
      const { event } = action;
      if (event.type === "done") return { ...job, status: "done", language: event.language };
      if (event.type === "finding") {
        // A resumed stream may repeat the last finding; one clause has one finding.
        return job.findings.some((found) => found.n === event.finding.n)
          ? job
          : { ...job, findings: [...job.findings, event.finding] };
      }
      const counted = event.done !== undefined && event.total !== undefined;
      return {
        ...job,
        stage: event.stage,
        clauses: counted ? { done: event.done ?? 0, total: event.total ?? 0 } : job.clauses,
      };
    }
  }
}
