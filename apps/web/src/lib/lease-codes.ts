// The lease check's stages and failure codes, apart from the transport that parses them, so the
// pages that only name them load no schema library (docs/notes/mobile-performance.md).

export const LEASE_STAGES = ["uploaded", "redacting", "reading", "checking"] as const;
export type LeaseStage = (typeof LEASE_STAGES)[number];

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
