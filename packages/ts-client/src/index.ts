/**
 * Plumbline's API types, generated from packages/ts-client/openapi.json (`make openapi`),
 * and a typed client for the JSON routes. The answer stream itself is read by the AI
 * SDK's `useChat`; its data-part payloads are typed here too.
 */
import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };
export type Schemas = components["schemas"];

export type Citation = Schemas["Citation"];
export type AnswerSummary = Schemas["AnswerSummary"];
export type TraceSummary = Schemas["TraceSummary"];
export type StatusEvent = Schemas["StatusEvent"];
export type AnswerStatus = Schemas["AnswerStatus"];
export type Jurisdiction = Schemas["Jurisdiction"];
export type Health = Schemas["Health"];

/** The data parts of Plumbline's UI message stream, keyed by part name ("data-<name>"). */
export type PlumblineDataParts = {
  status: StatusEvent;
  citation: Citation;
  answer: AnswerSummary;
  trace: TraceSummary;
};

export function createApiClient(baseUrl: string) {
  return createClient<paths>({ baseUrl });
}
