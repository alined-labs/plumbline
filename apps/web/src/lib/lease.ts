import type { Citation } from "@plumbline/ts-client";
import { z } from "zod";

import { JURISDICTION_IDS } from "./jurisdictions";

// The lease checker's findings, as Lane C defines them (apps/api/src/plumbline/leases/schema.py)
// and Lane D streams them from /api/check-lease. The schema validates each event as it
// arrives; when openapi.json carries the Finding, its type replaces this one and the schema
// stays as the runtime check.

export const SEVERITIES = ["conflict", "check", "note", "match"] as const;
export type Severity = (typeof SEVERITIES)[number];

// Typed as the generated client's Citation, so a change to either side fails to compile here.
const citationSchema: z.ZodType<Citation> = z.object({
  n: z.number().int().min(1),
  chunk_id: z.string().min(1),
  ref: z.object({
    jurisdiction: z.enum(JURISDICTION_IDS),
    law: z.string().min(1),
    article: z.string().min(1),
    paragraph: z.string().nullable(),
    edition: z.string().min(1),
  }),
  label: z.string().min(1),
  quote: z.string().min(1),
  gloss: z.string().nullable(),
  language: z.enum(["en", "es"]),
  verified: z.boolean(),
  page: z.number().int().min(1).nullable(),
});

export const findingSchema = z.object({
  n: z.number().int().min(1),
  clause_number: z.string().min(1),
  clause_text: z.string().min(1),
  clause_language: z.enum(["en", "es"]),
  severity: z.enum(SEVERITIES),
  title: z.string().min(1).max(120),
  why: z.string().min(1),
  citations: z.array(citationSchema).min(1),
  confidence: z.number().min(0).max(1),
});

export type Finding = z.infer<typeof findingSchema>;

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
