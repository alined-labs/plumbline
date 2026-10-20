import type { Jurisdiction, Schemas } from "@plumbline/ts-client";
import type { FieldError, Resolver, ResolverResult } from "react-hook-form";

import { JURISDICTION_IDS } from "./jurisdictions";

// The composer's own validation, written out rather than through a schema library: the chat
// page's first load then carries no zod (docs/notes/mobile-performance.md). Three rules, each
// with its fix in words.

/** The API's limit on a question (core/stream.py MAX_QUESTION_CHARS). */
export const MAX_QUESTION_CHARS = 2000;

export type AskValues = {
  question: string;
  /** Empty: let the API detect the jurisdiction from the question. */
  jurisdictions: Jurisdiction[];
  /** Empty: the law in force today. A filter on the law, never a hint to the model. */
  asOf: string;
};

/** A real calendar day written as YYYY-MM-DD: "2024-02-30" is not one. */
export function isIsoDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const [year, month, day] = match.slice(1).map(Number) as [number, number, number];
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
  );
}

type AskErrors = Partial<Record<keyof AskValues, FieldError>>;

/** The question trimmed, or the errors that say how to fix it (Field spec), in the form's
 * order: the question, then the jurisdictions, then the date. */
export function checkAsk(values: AskValues): ResolverResult<AskValues> {
  const question = values.question.trim();
  const errors: AskErrors = {};
  if (question === "") errors.question = { type: "required", message: "Write a question to ask" };
  else if (question.length > MAX_QUESTION_CHARS) {
    errors.question = {
      type: "maxLength",
      message: `Shorten the question to ${MAX_QUESTION_CHARS} characters or fewer`,
    };
  }
  const known: readonly string[] = JURISDICTION_IDS;
  if (!values.jurisdictions.every((id) => known.includes(id))) {
    errors.jurisdictions = { type: "enum", message: "Choose jurisdictions from the list" };
  }
  if (values.asOf !== "" && !isIsoDate(values.asOf)) {
    errors.asOf = { type: "date", message: "Enter the date as day, month and year" };
  }
  return Object.keys(errors).length > 0
    ? { values: {}, errors }
    : { values: { ...values, question }, errors: {} };
}

export const askResolver: Resolver<AskValues> = (values) => checkAsk(values);

export const EMPTY_ASK: AskValues = { question: "", jurisdictions: [], asOf: "" };

/** Plumbline's own fields of the /api/ask body; useChat adds the messages. */
export type AskBody = Required<Pick<Schemas["AskRequest"], "as_of" | "jurisdictions">>;

export function askBody({ jurisdictions, asOf }: AskValues): AskBody {
  return { as_of: asOf === "" ? null : asOf, jurisdictions };
}
