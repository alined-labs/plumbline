// @vitest-environment node
import { createApiClient } from "@plumbline/ts-client";
import { QueryClient } from "@tanstack/react-query";

import { ApiError, healthQuery } from "./api";

function clientAnswering(response: Response) {
  const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetch);
  // openapi-fetch reads globalThis.fetch when the client is created.
  return { fetch, client: createApiClient("http://api.test") };
}

afterEach(() => vi.unstubAllGlobals());

describe("healthQuery", () => {
  it("returns the typed health of the API", async () => {
    const body = { status: "ok", version: "0.1.0", tier: "free", cache_mode: "live" };
    const { fetch, client } = clientAnswering(Response.json(body));
    const health = await new QueryClient().fetchQuery(healthQuery(client));
    expect(health.tier).toBe("free");
    const request = fetch.mock.calls[0]?.[0];
    expect(request instanceof Request && request.url).toBe("http://api.test/api/health");
  });

  it("fails once, without retrying, when the API is not there", async () => {
    const { fetch, client } = clientAnswering(new Response("down", { status: 503 }));
    await expect(new QueryClient().fetchQuery(healthQuery(client))).rejects.toEqual(
      new ApiError("/api/health", 503),
    );
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
