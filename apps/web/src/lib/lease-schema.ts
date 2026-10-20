import type { Citation } from "@plumbline/ts-client";
import { z } from "zod";

import { JURISDICTION_IDS } from "./jurisdictions";
import { SEVERITIES } from "./lease";

// The lease checker's findings as Lane C defines them (apps/api/src/plumbline/leases/schema.py)
// and Lane D streams them from /api/check-lease: the runtime check of each event as it arrives.
// Apart from the helpers in lease.ts, so that what loads with every page (the toast that follows
// a check in the background) takes no schema with it. When openapi.json carries the Finding, its
// type replaces this one and the schema stays as the runtime check.

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
