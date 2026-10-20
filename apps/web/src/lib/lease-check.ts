import { z } from "zod";

import { apiUrl } from "./api";

// The lease check as a job, the way Lane D's route (D7) and Lane C's checker define it:
//   POST /api/check-lease?jurisdiction=&signed_on=    the file itself as the body -> 202 {id}
//   GET  /api/check-lease/{id}/events    server-sent events: stage*, finding*, then done or failed
// The lease is the raw body, not a multipart form, so the server never writes it to disk. A
// refusal is application/problem+json with a stable `code`. Until openapi.json carries the
// job, its shapes are read here and nowhere else, so a rename is a change to this file.

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
export type LeaseRequest = { file: File; jurisdiction: string; signedOn: string };

/** `fetch` and an abort signal, so a test can answer and a reader can cancel. */
export type Transport = { fetch?: typeof fetch; signal?: AbortSignal };

/** The network failed or the stream ended before `done` or `failed`: nothing the checker said. */
class Dropped extends Error {}

// A cancel passes through as the AbortError it is; any other failure to reach the service is
// a drop. The visitor cookie travels with every request, which is what the quota counts.
async function send(url: string, init: RequestInit, transport: Transport): Promise<Response> {
  try {
    return await (transport.fetch ?? fetch)(url, {
      credentials: "include",
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
