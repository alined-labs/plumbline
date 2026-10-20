import type { Schemas } from "@plumbline/ts-client";
import { z } from "zod";

import { JURISDICTION_IDS } from "./jurisdictions";

/** The API's limit on a question (core/stream.py MAX_QUESTION_CHARS). */
export const MAX_QUESTION_CHARS = 2000;

// Errors say how to fix the input, not what is wrong with it (Field spec).
export const askSchema = z.object({
  question: z
    .string()
    .trim()
    .min(1, "Write a question to ask")
    .max(MAX_QUESTION_CHARS, `Shorten the question to ${MAX_QUESTION_CHARS} characters or fewer`),
  // Empty: let the API detect the jurisdiction from the question.
  jurisdictions: z.array(z.enum(JURISDICTION_IDS)),
  // Empty: the law in force today. A filter on the law, never a hint to the model.
  asOf: z.union([z.literal(""), z.iso.date("Enter the date as day, month and year")]),
});

export type AskValues = z.infer<typeof askSchema>;

export const EMPTY_ASK: AskValues = { question: "", jurisdictions: [], asOf: "" };

/** Plumbline's own fields of the /api/ask body; useChat adds the messages. */
export type AskBody = Required<Pick<Schemas["AskRequest"], "as_of" | "jurisdictions">>;

export function askBody({ jurisdictions, asOf }: AskValues): AskBody {
  return { as_of: asOf === "" ? null : asOf, jurisdictions };
}
