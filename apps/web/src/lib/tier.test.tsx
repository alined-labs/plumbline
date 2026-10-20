import { renderHook, waitFor } from "@testing-library/react";

import { api } from "./api";
import { QueryWrapper } from "@/test/query";

import { useDemoMode } from "./tier";

afterEach(() => vi.restoreAllMocks());

function answer(result: { tier: string } | "unreachable") {
  vi.spyOn(api, "GET").mockImplementation((async () => {
    if (result === "unreachable") throw new TypeError("Failed to fetch");
    return { data: { ...result, updated_at: null }, error: undefined, response: new Response() };
  }) as unknown as typeof api.GET);
}

describe("useDemoMode", () => {
  it("is live on the full and free tiers, after checking", async () => {
    answer({ tier: "free" });
    const { result } = renderHook(useDemoMode, { wrapper: QueryWrapper });
    expect(result.current).toBe("checking");
    await waitFor(() => expect(result.current).toBe("live"));
  });

  it("replays on the static tier", async () => {
    answer({ tier: "static" });
    const { result } = renderHook(useDemoMode, { wrapper: QueryWrapper });
    await waitFor(() => expect(result.current).toBe("replay"));
  });

  it("stays live when the API does not answer, so the page does not change under the reader", async () => {
    answer("unreachable");
    const { result } = renderHook(useDemoMode, { wrapper: QueryWrapper });
    await waitFor(() => expect(result.current).toBe("live"));
  });
});
