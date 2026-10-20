import type { Jurisdiction } from "@plumbline/ts-client";
import { z } from "zod";

import { apiUrl, WITH_COOKIE } from "./api";
import type { Finding } from "./lease";
import { findingSchema } from "./lease-schema";
import { readSse, type SseEvent } from "./sse";

// The lease check as a job, the way Lane D's route (D7) and Lane C's checker define it:
//   POST /api/check-lease?jurisdiction=&signed_on=    the file itself as the body -> 202 {id}
//   GET  /api/check-lease/{id}/events    server-sent events: stage*, finding*, then done or failed
// The lease is the raw body, not a multipart form, so the server never writes it to disk. A
// refusal is application/problem+json with a stable `code`. Until openapi.json carries the
// job, its shapes are read here and nowhere else, so a rename is a change to this file.

export const LEASE_STAGES = ["uploaded", "redacting", "reading", "checking"] as const;
export type LeaseStage = (typeof LEASE_STAGES)[number];

export type LeaseEvent =
  | { type: "stage"; stage: LeaseStage; done?: number; total?: number }
  | { type: "finding"; finding: Finding }
  | { type: "done"; findings: number; language: "en" | "es" };

const stageSchema = z.object({
  stage: z.enum(LEASE_STAGES),
  done: z.number().int().min(0).optional(),
  total: z.number().int().min(0).optional(),
});
const doneSchema = z.object({ findings: z.number().int().min(0), language: z.enum(["en", "es"]) });
const failedSchema = z.object({ code: z.string().min(1), message: z.string() });
const problemSchema = z.object({
  code: z.string().min(1).optional(),
  title: z.string().optional(),
  detail: z.string().optional(),
});

/** The codes the page words itself. Lane D's: the upload, the quota and the run. Lane C's: the
 * checker. The last is this page's own: the stream dropped and could not be picked up. */
export const FAILURE_CODES = [
  "unsupported_type",
  "too_large",
  "unreadable",
  "quota_reached",
  "not_found",
  "lease_checks_paused",
  "busy",
  "unavailable",
  "timed_out",
  "interrupted",
  "internal",
  "redaction_refused",
  "jurisdiction_unknown",
  "no_clauses",
  "connection_lost",
] as const;
export type FailureCode = (typeof FAILURE_CODES)[number];

export function isFailureCode(code: string): code is FailureCode {
  return (FAILURE_CODES as readonly string[]).includes(code);
}

/** A check that cannot go on. `code` is the server's, so one this page has no words for still
 * arrives with the server's `message`. */
export class LeaseFailure extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "LeaseFailure";
  }
}

const CODE_BY_STATUS: Partial<Record<number, FailureCode>> = {
  404: "not_found",
  413: "too_large",
  415: "unsupported_type",
  422: "unreadable",
  429: "quota_reached",
};

/** What the page sends for a lease: the form's values, "" for an optional one left empty. */
export type LeaseRequest = { file: File; jurisdiction: "" | Jurisdiction; signedOn: string };

/** `fetch` and an abort signal, so a test can answer and a reader can cancel. */
export type Transport = { fetch?: typeof fetch; signal?: AbortSignal };

/** The network failed or the stream ended before `done` or `failed`: nothing the checker said. */
class Dropped extends Error {}

// A cancel passes through as the AbortError it is; any other failure to reach the service is
// a drop. The visitor cookie travels with every request, which is what the quota counts.
async function send(url: string, init: RequestInit, transport: Transport): Promise<Response> {
  try {
    return await (transport.fetch ?? fetch)(url, {
      ...WITH_COOKIE,
      ...init,
      signal: transport.signal,
    });
  } catch (error) {
    if (transport.signal?.aborted) throw error;
    throw new Dropped();
  }
}

async function refusal(response: Response): Promise<LeaseFailure> {
  const parsed = problemSchema.safeParse(await response.json().catch(() => null));
  const problem = parsed.success ? parsed.data : {};
  const seconds = Number(response.headers.get("Retry-After"));
  return new LeaseFailure(
    problem.code ?? CODE_BY_STATUS[response.status] ?? "unavailable",
    problem.detail ?? problem.title ?? `The lease checker answered ${response.status}.`,
    seconds > 0 ? seconds : undefined,
  );
}

/** Sends the lease and returns the job's ID. */
export async function startLeaseCheck(
  request: LeaseRequest,
  transport: Transport = {},
): Promise<string> {
  const query = new URLSearchParams();
  if (request.jurisdiction) query.set("jurisdiction", request.jurisdiction);
  if (request.signedOn) query.set("signed_on", request.signedOn);
  const unavailable = new LeaseFailure("unavailable", "The lease checker didn't answer.");
  const response = await send(
    `${apiUrl("/api/check-lease")}${query.size > 0 ? `?${query}` : ""}`,
    { method: "POST", body: request.file },
    transport,
  ).catch((error: unknown) => {
    throw error instanceof Dropped ? unavailable : error;
  });
  if (!response.ok) throw await refusal(response);
  const job = z
    .object({ id: z.string().min(1) })
    .safeParse(await response.json().catch(() => null));
  if (!job.success) throw unavailable;
  return job.data.id;
}

const UNREADABLE = "The lease checker sent something this page can't read.";

function parseEvent(sse: SseEvent): LeaseEvent | undefined {
  // Anything else (a comment, a keep-alive) is not ours to read.
  if (!["stage", "finding", "done", "failed"].includes(sse.event)) return undefined;
  let payload: unknown;
  try {
    payload = JSON.parse(sse.data);
  } catch {
    throw new LeaseFailure("unavailable", UNREADABLE);
  }
  if (sse.event === "failed") {
    const failed = failedSchema.safeParse(payload);
    if (!failed.success) throw new LeaseFailure("unavailable", UNREADABLE);
    throw new LeaseFailure(failed.data.code, failed.data.message);
  }
  // A finding that does not match Lane C's schema is an error, not a gap: dropping it quietly
  // could hide a conflict.
  if (sse.event === "finding") {
    const finding = findingSchema.safeParse(payload);
    if (!finding.success) throw new LeaseFailure("unavailable", UNREADABLE);
    return { type: "finding", finding: finding.data };
  }
  if (sse.event === "stage") {
    const stage = stageSchema.safeParse(payload);
    if (!stage.success) throw new LeaseFailure("unavailable", UNREADABLE);
    return { type: "stage", ...stage.data };
  }
  const done = doneSchema.safeParse(payload);
  if (!done.success) throw new LeaseFailure("unavailable", UNREADABLE);
  return { type: "done", ...done.data };
}

/** How many times a dropped stream is picked up again, and how long the first wait is. */
const MAX_RESUMES = 3;
const RESUME_WAIT_MS = 500;

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}

/** The job's events until `done`, which ends the iteration, or `failed`, which throws. A stream
 * that drops before either is picked up again from the last event ID, up to three times in a
 * row; a server that sends no IDs cannot be resumed, so the check ends as a lost connection. */
export async function* leaseEvents(
  id: string,
  transport: Transport = {},
): AsyncGenerator<LeaseEvent> {
  let lastEventId: string | undefined;
  let resumes = 0;
  for (;;) {
    try {
      const headers: Record<string, string> = { Accept: "text/event-stream" };
      if (lastEventId !== undefined) headers["Last-Event-ID"] = lastEventId;
      const response = await send(
        apiUrl(`/api/check-lease/${encodeURIComponent(id)}/events`),
        { headers, cache: "no-store" },
        transport,
      );
      if (!response.ok || !response.body) throw await refusal(response);
      for await (const sse of readSse(response.body)) {
        resumes = 0; // a stream that moves on has not given up
        lastEventId = sse.lastEventId ?? lastEventId;
        const event = parseEvent(sse);
        if (event) yield event;
        if (event?.type === "done") return;
      }
      throw new Dropped();
    } catch (error) {
      // What the checker said (a refusal, a failure) and a cancel end the check as they are.
      // Anything else is the connection: picked up again where it stopped, if it can be.
      if (error instanceof LeaseFailure || transport.signal?.aborted) throw error;
      if (lastEventId === undefined || resumes >= MAX_RESUMES) {
        throw new LeaseFailure("connection_lost", "The connection to the lease checker dropped.");
      }
      resumes += 1;
      await wait(RESUME_WAIT_MS * resumes, transport.signal);
    }
  }
}
