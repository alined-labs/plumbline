// Test fixtures for the cited article: what GET /api/chunks/{id} answers, and a stand-in for it.
import { vi } from "vitest";

import { api } from "@/lib/api";
import type { ChunkArticle } from "@/lib/article";

const TEXT =
  "(3)(a) Upon the vacating of the premises for termination of the lease, if the landlord does not intend to impose a claim on the security deposit, the landlord shall have 15 days to return the security deposit together with interest if otherwise required.";
const QUOTE = "the landlord shall have 15 days to return the security deposit";
const START = Array.from(TEXT.slice(0, TEXT.indexOf(QUOTE))).length;

export const ARTICLE: ChunkArticle = {
  chunk_id: "fl-83-49",
  article: {
    ref: {
      jurisdiction: "florida",
      law: "fl-stat-83",
      article: "83.49",
      paragraph: null,
      edition: "2026",
    },
    label: "Fla. Stat. § 83.49",
    heading: "Deposit money or advance rent; duty of landlord and tenant",
    text: TEXT,
    language: "en",
    page: null,
    status: "in_force",
    validity_note: null,
    effective_from: "2013-07-01",
    effective_to: null,
  },
  span: { start: START, end: START + Array.from(QUOTE).length },
  source: {
    id: "fl-stat-83-2026",
    title: "Florida Statutes 2026, chapter 83",
    url: "https://www.leg.state.fl.us/",
  },
};

/** Stands in for the article route: an article, a refusal, or no answer yet. */
export function mockArticle(answer: ChunkArticle | "refused" | "pending") {
  return vi.spyOn(api, "GET").mockImplementation((async () => {
    if (answer === "pending") return new Promise(() => {});
    if (answer === "refused") {
      return { data: undefined, error: {}, response: new Response(null, { status: 503 }) };
    }
    return { data: answer, error: undefined, response: new Response(null, { status: 200 }) };
  }) as unknown as typeof api.GET);
}
