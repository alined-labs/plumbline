import type { Schemas } from "@plumbline/ts-client";
import { queryOptions } from "@tanstack/react-query";

import { api, ApiError, type ApiClient } from "./api";
import { formatClock, untilUtcMidnight } from "./dates";

export type Usage = Schemas["Usage"];

/** Today's questions for this visitor and their address, which count nothing themselves and set
 * no cookie (GET /api/usage). Refetched after each answer; a failure is an answer too (the
 * static tier has no API), so it is not retried. */
export function usageQuery(client: ApiClient = api) {
  return queryOptions({
    queryKey: ["usage"],
    queryFn: async ({ signal }) => {
      const { data, response } = await client.GET("/api/usage", { signal });
      if (!data) throw new ApiError("/api/usage", response.status);
      return data;
    },
    staleTime: 30_000,
    retry: false,
  });
}

/** From 80% of the allowance used, the meter turns to a warning and says how many are left. */
const LOW_SHARE = 0.8;

/** How the UsageMeter spec reads a count: the numbers, whether the meter is low or spent, and
 * its words. Code works out every number; nothing here is left to a model or to the reader. */
export function usageView(usage: Usage, now: Date) {
  const { limit, resets_at } = usage;
  const used = Math.min(usage.used, limit);
  const left = limit - used;
  const share = limit > 0 ? used / limit : 1;
  const low = share >= LOW_SHARE;
  const resets = formatClock(resets_at);
  return {
    used,
    limit,
    left,
    share,
    low,
    exhausted: left === 0,
    count: `${used} of ${limit}`,
    note: low
      ? `${left === 0 ? "None" : left} left today · resets at ${resets}`
      : `Resets at ${resets}`,
    /** The composer's words when nothing is left. */
    composerReason: `Demo questions reset at ${resets}, in ${untilUtcMidnight(now)}.`,
  };
}
