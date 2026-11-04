import type { Schemas } from "@plumbline/ts-client";
import { queryOptions } from "@tanstack/react-query";

import { api, ApiError, WITH_COOKIE, type ApiClient } from "./api";

export type ChunkArticle = Schemas["ChunkArticle"];
export type PublishedArticle = Schemas["PublishedArticle"];

/** The cited article as published, with the cited quote's place in it (GET /api/chunks/{id}).
 * An article changes only with an edition, so a minute is a short time to keep one. */
export function articleQuery(chunkId: string, quote: string, client: ApiClient = api) {
  return queryOptions({
    queryKey: ["article", chunkId, quote],
    queryFn: async ({ signal }) => {
      const { data, response } = await client.GET("/api/chunks/{chunk_id}", {
        params: { path: { chunk_id: chunkId }, query: { quote } },
        signal,
        ...WITH_COOKIE,
      });
      if (!data) throw new ApiError("/api/chunks", response.status);
      return data;
    },
    staleTime: 60_000,
    retry: false,
  });
}

/** The article's text cut around the cited span. The API counts characters in Unicode code
 * points and JavaScript strings count UTF-16 units, so the cut goes through code points: an
 * astral character before the span would otherwise shift it. Null when there is no span, or it
 * does not fit the text. */
export function splitAtSpan(
  text: string,
  span: { start: number; end: number } | null,
): { before: string; cited: string; after: string } | null {
  if (!span) return null;
  const chars = Array.from(text);
  if (span.start < 0 || span.start >= span.end || span.end > chars.length) return null;
  return {
    before: chars.slice(0, span.start).join(""),
    cited: chars.slice(span.start, span.end).join(""),
    after: chars.slice(span.end).join(""),
  };
}

/** "Characters 1,204 to 1,330 of 2,340": where the quote sits in the article, counted the way
 * the API counts (code points), from 1. */
export function spanRange(text: string, span: { start: number; end: number }): string {
  const number = new Intl.NumberFormat("en-GB");
  const total = Array.from(text).length;
  return `Characters ${number.format(span.start + 1)} to ${number.format(span.end)} of ${number.format(total)}`;
}
