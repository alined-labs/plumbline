import { createApiClient } from "@plumbline/ts-client";
import { queryOptions } from "@tanstack/react-query";

/** Where the browser finds the API. The static export is built once, so this is public. */
export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export function apiUrl(path: `/api/${string}`): string {
  return `${API_BASE_URL}${path}`;
}

export type ApiClient = ReturnType<typeof createApiClient>;

/** The site and the API are different origins (plumbline. and plumbline-api.alinedlabs.co), and
 * a browser sends and keeps a cookie across origins only when the request asks it to. Every call
 * that counts a visitor, or is counted by one, carries the visitor cookie this way; the API
 * allows it for the site's origin alone (CORS with credentials). */
export const WITH_COOKIE = { credentials: "include" } as const satisfies RequestInit;

/** The typed client for the JSON routes; the answer stream goes through useChat instead. */
export const api: ApiClient = createApiClient(API_BASE_URL);

export class ApiError extends Error {
  constructor(
    readonly route: string,
    readonly status: number,
  ) {
    super(`${route} answered ${status}`);
    this.name = "ApiError";
  }
}

/** The API's health and current demo tier. The static tier has no API, so a failure is an
 * answer ("live answers are off"), not something to retry. */
export function healthQuery(client: ApiClient = api) {
  return queryOptions({
    queryKey: ["health"],
    queryFn: async ({ signal }) => {
      const { data, response } = await client.GET("/api/health", { signal });
      if (!data) throw new ApiError("/api/health", response.status);
      return data;
    },
    retry: false,
    staleTime: 30_000,
  });
}
