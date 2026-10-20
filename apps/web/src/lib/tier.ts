import { queryOptions, useQuery } from "@tanstack/react-query";

import { api, ApiError, WITH_COOKIE, type ApiClient } from "./api";

// Which demo the page is: the live chat, or the static tier's replay of stored answers. The API
// says so (GET /api/settings/tier). An API that does not answer leaves the page live: swapping
// the empty state and the composer for the replay after the page has drawn moves the whole page
// (a layout shift of 0.68 on a phone), so the reader is offered the replay when a question fails
// instead.

export function tierQuery(client: ApiClient = api) {
  return queryOptions({
    queryKey: ["tier"],
    queryFn: async ({ signal }) => {
      const { data, response } = await client.GET("/api/settings/tier", { signal, ...WITH_COOKIE });
      if (!data) throw new ApiError("/api/settings/tier", response.status);
      return data.tier;
    },
    // The tier changes only when the operator flips it; a page keeps the one it opened with.
    staleTime: Infinity,
    retry: false,
  });
}

export type DemoMode = "checking" | "live" | "replay";

/** "replay" when the API says the tier is static; "checking" until it answers; "live"
 * otherwise, including when it does not answer at all. */
export function useDemoMode(): DemoMode {
  const { data, isError } = useQuery(tierQuery());
  if (data === "static") return "replay";
  return data === undefined && !isError ? "checking" : "live";
}
