import { untilUtcMidnight } from "./dates";
import { isFailureCode, type FailureCode } from "./lease-codes";
import type { JobFailure } from "./lease-job";
import { MAX_LEASE_MB } from "./lease-file";

/** What the page offers after a failure: the same file again, another file, the jurisdiction
 * field, or nothing (the reader waits). */
export type NextStep = "retry" | "choose-file" | "choose-jurisdiction" | "none";

export type FailureCopy = {
  title: string;
  /** The first sentence, set bold: it carries the fix (ErrorState spec). */
  lead: string;
  body?: string;
  next: NextStep;
};

const RETRY = "Your file is kept; try again in a moment.";

// One entry per code the page knows, worded for the reader: the title names what failed, the
// lead says what to do. Several are the ErrorState spec's own ("This lease couldn't be read").
function copyFor(code: FailureCode, failure: JobFailure, now: Date): FailureCopy {
  switch (code) {
    case "unsupported_type":
      return {
        title: "This file can't be checked",
        lead: "Upload a PDF or a DOCX.",
        body: "Pictures, spreadsheets and other formats aren't supported.",
        next: "choose-file",
      };
    case "too_large":
      return {
        title: "This lease is too large",
        lead: `Choose a file of ${MAX_LEASE_MB} MB or less.`,
        next: "choose-file",
      };
    case "unreadable":
      return {
        title: "This lease couldn't be read",
        lead: "The file has no selectable text.",
        body: "If it's a scan, upload a text PDF or a DOCX instead: Plumbline can't read scanned pages.",
        next: "choose-file",
      };
    case "no_clauses":
      return {
        title: "Plumbline found no clauses to check",
        lead: "It looks for numbered clauses, and this lease has none it could read.",
        body: "Check that each clause starts with its number, such as 1. or 2.1, or upload another file.",
        next: "choose-file",
      };
    case "jurisdiction_unknown":
      return {
        title: "Which law governs this lease?",
        lead: "Choose where the property is.",
        body: "Plumbline couldn't tell from the lease, and it doesn't guess.",
        next: "choose-jurisdiction",
      };
    case "quota_reached":
      return {
        title: "Today's demo checks are used up",
        lead: `They reset at 00:00 UTC, in ${untilUtcMidnight(now)}.`,
        body: "The evaluation and the statutes' dates stay open.",
        next: "none",
      };
    case "lease_checks_paused":
      return {
        title: "Lease checks are paused",
        lead: "The demo is on its free tier, which can't check leases.",
        body: "Questions about the law still work.",
        next: "none",
      };
    case "busy":
      return {
        title: "Plumbline is checking another lease",
        lead: `Try again in ${failure.retryAfter ?? 30} seconds.`,
        body: "The demo checks one lease at a time for each visitor.",
        next: "retry",
      };
    case "redaction_refused":
      return {
        title: "This lease can't be checked yet",
        lead: "Plumbline can't redact uploads right now, so it didn't read the file.",
        body: "Nothing was sent to a model. Try again later.",
        next: "retry",
      };
    case "unavailable":
      return {
        title: "Plumbline couldn't reach the lease checker",
        lead: "The service didn't answer.",
        body: RETRY,
        next: "retry",
      };
    case "connection_lost":
      return {
        title: "The connection dropped",
        lead: "The check stopped when the connection to the lease checker dropped.",
        body: RETRY,
        next: "retry",
      };
    case "timed_out":
      return {
        title: "The check took too long",
        lead: "Plumbline stopped it at the time limit.",
        body: "Try again, or upload a shorter lease.",
        next: "retry",
      };
    case "interrupted":
      return {
        title: "The check was interrupted",
        lead: "The service restarted while it was running.",
        body: RETRY,
        next: "retry",
      };
    case "internal":
      return {
        title: "The check failed",
        lead: "That's on Plumbline, not on your file.",
        body: "Try again; if it keeps failing, quote the error ID below.",
        next: "retry",
      };
    case "not_found":
      return {
        title: "That check has expired",
        lead: "Checks are kept for 30 minutes.",
        body: "Upload the lease again to start a new one.",
        next: "choose-file",
      };
  }
}

/** The words for a failure. A code the page has no words for keeps the server's message. */
export function failureCopy(failure: JobFailure, now: Date): FailureCopy {
  if (isFailureCode(failure.code)) return copyFor(failure.code, failure, now);
  return {
    title: "The lease check stopped",
    lead: failure.message,
    body: "Try again; if it keeps failing, quote the error ID below.",
    next: "retry",
  };
}

/** Failures that are not a view that broke but a state of the demo or a missing answer: shown
 * as a callout above the form, which stays with the reader's file, instead of replacing the
 * page. */
export function showsOnForm(failure: JobFailure): boolean {
  return ["quota_reached", "lease_checks_paused", "jurisdiction_unknown"].includes(failure.code);
}
