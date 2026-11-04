"use client";

import dynamic from "next/dynamic";

// The nightly table fetches from the API in the browser and sits below the fold, so it loads on
// its own once the page has drawn: the page's first load stays the export's own (the query
// library and the API client cost /evals 34 kB when it was imported directly).
export const OnlineNightsLazy = dynamic(
  () => import("./online-nights").then((module) => module.OnlineNights),
  { ssr: false },
);
