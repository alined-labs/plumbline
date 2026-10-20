import { queryOptions } from "@tanstack/react-query";

import { apiUrl } from "./api";

// The nightly online evaluation (Lane P's job, Lane D's GET /api/evals/online): a sample of the
// previous day's production answers judged for faithfulness, the last 14 nights newest first.
// Fetched in the browser, since the export cannot know last night at build time.

/** One night, as the API's OnlineNight writes it. */
export type OnlineNight = {
  day: string;
  config_name: string;
  answered: number;
  sampled: number;
  judged: number;
  faithful: number;
  faithfulness: number | null;
  interval_95: [number, number] | null;
};

export function onlineQuery() {
  return queryOptions({
    queryKey: ["evals-online"],
    queryFn: async ({ signal }): Promise<OnlineNight[]> => {
      const response = await fetch(apiUrl("/api/evals/online"), { signal });
      if (!response.ok) throw new Error(`/api/evals/online answered ${response.status}`);
      const body = (await response.json()) as OnlineNight[] | { runs: OnlineNight[] };
      return Array.isArray(body) ? body : body.runs;
    },
    // The nights change once a day; the API caches the answer for an hour.
    staleTime: 60 * 60_000,
    retry: false,
  });
}

/** The nights worth showing: those with judged answers. */
export function judgedNights(nights: readonly OnlineNight[]): OnlineNight[] {
  return nights.filter((night) => night.judged > 0 && night.faithfulness !== null);
}
