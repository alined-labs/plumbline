import type { Jurisdiction } from "@plumbline/ts-client";

import { JURISDICTION_IDS } from "./jurisdictions";

// Which jurisdictions the live site can answer from: all four, less those production has not
// indexed yet (NEXT_PUBLIC_UNINDEXED, a comma list set by the deploy, e.g. "dubai,colombia").
// The site then offers no example question and no invented lease it cannot answer: a lease
// checked against a law that is not indexed would come back with no findings, wrongly.

export function parseUnindexed(raw: string | undefined): Jurisdiction[] {
  const named = (raw ?? "")
    .split(",")
    .map((name) => name.trim().toLowerCase())
    .filter(Boolean);
  return JURISDICTION_IDS.filter((id) => named.includes(id));
}

export const UNINDEXED: readonly Jurisdiction[] = parseUnindexed(process.env.NEXT_PUBLIC_UNINDEXED);

export function isIndexed(id: Jurisdiction, unindexed: readonly Jurisdiction[] = UNINDEXED) {
  return !unindexed.includes(id);
}
