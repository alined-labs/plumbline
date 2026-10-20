import { queryOptions, useQuery } from "@tanstack/react-query";

import { api, ApiError, type ApiClient } from "./api";

// Which demo the page is: the live chat, or the static tier's replay of stored answers. The API
// says so (GET /api/settings/tier); when it cannot be reached at all, the export is being served
// without it, which is the static tier too.

export function tierQuery(client: ApiClient = api) {
  return queryOptions({
    queryKey: ["tier"],
    queryFn: async ({ signal }) => {
      const { data, response } = await client.GET("/api/settings/tier", { signal });
      if (!data) throw new ApiError("/api/settings/tier", response.status);
      return data.tier;
    },
    // The tier changes only when the operator flips it; a page keeps the one it opened with.
    staleTime: Infinity,
    retry: false,
  });
}

export type DemoMode = "checking" | "live" | "replay";

/** "replay" when the tier is static or the API does not answer; "checking" until it does. */
export function useDemoMode(): DemoMode {
  const { data, isError } = useQuery(tierQuery());
  if (isError || data === "static") return "replay";
  return data === undefined ? "checking" : "live";
}
