import type { Schemas } from "@plumbline/ts-client";

export type FeedbackRequest = Schemas["FeedbackRequest"];
export type FeedbackReason = NonNullable<FeedbackRequest["reasons"]>[number];

/** The Feedback spec's reasons, in its order: five a reader can choose in a second. */
export const FEEDBACK_REASONS = [
  { id: "wrong_citation", label: "Wrong citation" },
  { id: "missed_statute", label: "Missed a statute" },
  { id: "outdated_law", label: "Outdated law" },
  { id: "hard_to_follow", label: "Hard to follow" },
  { id: "something_else", label: "Something else" },
] as const satisfies readonly { id: FeedbackReason; label: string }[];

/** The longest note the API takes. */
export const MAX_NOTE = 1000;

/** What goes to POST /api/feedback. A note of spaces is no note; reasons are sent in the
 * spec's order, whatever order they were chosen in. */
export function feedbackBody(
  requestId: string,
  verdict:
    { helpful: true } | { helpful: false; reasons: ReadonlySet<FeedbackReason>; note: string },
): FeedbackRequest {
  if (verdict.helpful) return { request_id: requestId, helpful: true };
  const note = verdict.note.trim();
  return {
    request_id: requestId,
    helpful: false,
    reasons: FEEDBACK_REASONS.map((reason) => reason.id).filter((id) => verdict.reasons.has(id)),
    note: note === "" ? null : note,
  };
}
