// Test fixtures for the lease page: synthetic findings, the way Lane C's checker words them.
import type { Finding } from "@/lib/lease";

export const WAIVER: Finding = {
  n: 1,
  clause_number: "12.3",
  clause_text:
    "The Tenant waives all rights and remedies under the Florida Residential Landlord and Tenant Act.",
  clause_language: "en",
  severity: "conflict",
  title: "The clause waives rights the law gives the tenant",
  why: "Florida law makes a clause void to the extent that it waives the tenant's rights under this part. A blanket waiver like this one cannot take those rights away.",
  citations: [
    {
      n: 1,
      chunk_id: "fl-stat-83-47-1-a",
      ref: {
        jurisdiction: "florida",
        law: "fl-stat-83",
        article: "83.47",
        paragraph: "(1)(a)",
        edition: "2026",
      },
      label: "Fla. Stat. § 83.47(1)(a)",
      quote:
        "Purports to waive or preclude the rights, remedies, or requirements set forth in this part.",
      gloss: null,
      language: "en",
      verified: true,
      page: null,
    },
  ],
  confidence: 0.86,
};

export function finding(overrides: Partial<Finding> = {}): Finding {
  return { ...WAIVER, ...overrides };
}
