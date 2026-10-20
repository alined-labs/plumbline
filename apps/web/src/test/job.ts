// Test fixtures for a lease check's state: the actions the provider dispatches, built by hand.
import type { LeaseEvent, LeaseStage } from "@/lib/lease-check";
import {
  IDLE,
  reduceJob,
  type JobAction,
  type JobFailure,
  type LeaseJob,
  type StartedJob,
} from "@/lib/lease-job";

import { finding } from "./lease";

export const file = { name: "lease.pdf", size: 1_400_000 };

export function run(...actions: JobAction[]): LeaseJob {
  return actions.reduce(reduceJob, IDLE);
}

export const start: JobAction = { type: "start", file };
export const event = (e: LeaseEvent): JobAction => ({ type: "event", event: e });
export const stage = (name: LeaseStage, done?: number, total?: number) =>
  event({ type: "stage", stage: name, done, total });
export const found = (n: number, severity: "conflict" | "check" = "conflict") =>
  event({ type: "finding", finding: finding({ n, severity }) });
export const done = event({ type: "done", findings: 1, language: "en" });
export const failure: JobFailure = { code: "timed_out", message: "The check took too long." };

/** The state after a start and then the given actions; fails the test if nothing started. */
export function started(...actions: JobAction[]): StartedJob {
  const job = run(start, ...actions);
  if (job.status === "idle") throw new Error("the check did not start");
  return job;
}
