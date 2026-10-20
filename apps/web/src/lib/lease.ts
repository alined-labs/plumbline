import type { Citation } from "@plumbline/ts-client";

import type { Finding } from "./lease-schema";

// What the lease page does with the findings the checker returns, apart from the schemas that
// read them (lease-schema.ts): their severities, groups and counts.

export type { Finding };

export const SEVERITIES = ["conflict", "check", "note", "match"] as const;
export type Severity = (typeof SEVERITIES)[number];

/** How each severity reads: its badge tone and word (Badge spec), its group heading
 * (FindingCard spec) and the summary phrase, which agrees with its count. */
export const SEVERITY_INFO = {
  conflict: {
    tone: "danger",
    word: "Conflicts",
    group: "Conflicts with the law",
    summary: (count: number) => (count === 1 ? "conflicts with the law" : "conflict with the law"),
  },
  check: {
    tone: "warning",
    word: "Worth checking",
    group: "Worth checking",
    summary: () => "worth checking",
  },
  note: {
    tone: "info",
    word: "Note",
    group: "Notes",
    summary: (count: number) => (count === 1 ? "note" : "notes"),
  },
  match: {
    tone: "success",
    word: "Matches the law",
    group: "Matches the law",
    summary: (count: number) => (count === 1 ? "matches the law" : "match the law"),
  },
} as const satisfies Record<
  Severity,
  {
    tone: "danger" | "warning" | "info" | "success";
    word: string;
    group: string;
    summary: (count: number) => string;
  }
>;

/** The citations a finding may show: verified ones only. An unverified citation is dropped,
 * never shown in a weaker style, and a finding left with none has nothing to stand on. */
export function shownCitations(finding: Finding): Citation[] {
  return finding.citations.filter((citation) => citation.verified);
}

export type FindingGroup = { severity: Severity; findings: Finding[] };

/** Findings in the four groups, most pressing first, each in clause order; empty groups are
 * left out. There is no score or grade for the lease as a whole, only these groups. */
export function groupFindings(findings: readonly Finding[]): FindingGroup[] {
  return SEVERITIES.map((severity) => ({
    severity,
    findings: findings
      .filter((finding) => finding.severity === severity && shownCitations(finding).length > 0)
      .sort((a, b) => a.n - b.n),
  })).filter((group) => group.findings.length > 0);
}

/** The counts of the findings that are shown, as a phrase in the groups' order: "2 conflict with
 * the law, 1 worth checking". Code counts them; no model words a number. */
export function summarize(findings: readonly Finding[]): { total: number; text: string } {
  const groups = groupFindings(findings);
  return {
    total: groups.reduce((sum, group) => sum + group.findings.length, 0),
    text: groups
      .map(
        ({ severity, findings: inGroup }) =>
          `${inGroup.length} ${SEVERITY_INFO[severity].summary(inGroup.length)}`,
      )
      .join(", "),
  };
}
