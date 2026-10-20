import { summarize } from "./lease";
import type { LeaseStage } from "./lease-check";
import type { LeaseJob, StartedJob } from "./lease-job";

// What the lease page shows of a check, derived from its state: the four steps of the Dropzone
// spec, a progress value and the line a screen reader hears.

export type StepState = "done" | "active" | "pending" | "failed";
export type Step = { key: LeaseStage; label: string; state: StepState; detail?: string };

const STEPS = [
  { key: "uploaded", active: "Uploading", done: "Uploaded" },
  { key: "redacting", active: "Redacting", done: "Redacted" },
  { key: "reading", active: "Reading", done: "Read" },
  { key: "checking", active: "Checking clauses", done: "Checked clauses" },
] as const satisfies readonly { key: LeaseStage; active: string; done: string }[];

// How many steps are finished when the checker last reported a stage. It reports a stage as it
// enters it, except `uploaded`, which it reports once the upload is complete.
const FINISHED: Record<LeaseStage, number> = { uploaded: 1, redacting: 1, reading: 2, checking: 3 };

/** The four steps of the Dropzone spec: finished ones, the one under way (or the one a failure
 * stopped) and those still to come. */
export function steps(job: StartedJob): Step[] {
  const finished = job.status === "done" ? STEPS.length : job.stage ? FINISHED[job.stage] : 0;
  return STEPS.map((step, index): Step => {
    const state: StepState =
      index < finished
        ? "done"
        : index > finished
          ? "pending"
          : job.status === "failed"
            ? "failed"
            : job.status === "running"
              ? "active"
              : "pending";
    const counted = step.key === "checking" ? job.clauses : null;
    return {
      key: step.key,
      label:
        state === "done"
          ? counted
            ? `Checked ${counted.total} ${counted.total === 1 ? "clause" : "clauses"}`
            : step.done
          : step.active,
      state,
      detail: state === "active" && counted ? `${counted.done} of ${counted.total}` : undefined,
    };
  });
}

/** How far the check has got, 0 to 1, once the checker counts clauses; null before that, for a
 * bar that is not a promise about time. */
export function progress(job: StartedJob): number | null {
  if (job.status === "done") return 1;
  return job.clauses && job.clauses.total > 0 ? job.clauses.done / job.clauses.total : null;
}

/** What a screen reader hears when the check moves on: the step under way, then the result.
 * Clause counts are left out so that the line does not change fourteen times. */
export function announcement(job: LeaseJob): string {
  if (job.status === "idle" || job.status === "failed") return ""; // a failure announces itself
  if (job.status === "done") {
    const { total, text } = summarize(job.findings);
    return total === 0
      ? "Lease checked: no findings."
      : `Lease checked: ${total} ${total === 1 ? "finding" : "findings"}. ${text}.`;
  }
  const active = steps(job).find((step) => step.state === "active");
  return active ? `${active.label}…` : "";
}
