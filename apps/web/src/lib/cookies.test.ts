import type { ApiClient } from "./api";
import { articleQuery } from "./article";
import { tierQuery } from "./tier";
import { usageQuery } from "./usage";

// The site and the API are different origins: each visitor-scoped call must ask the browser to
// send the visitor cookie, or the API counts every question by address alone.
function client() {
  const GET = vi.fn(async () => ({ data: {}, error: undefined, response: new Response() }));
  return { client: { GET } as unknown as ApiClient, GET };
}

async function run(options: { queryFn?: unknown }) {
  const queryFn = options.queryFn as (context: { signal: AbortSignal }) => Promise<unknown>;
  await queryFn({ signal: new AbortController().signal }).catch(() => undefined);
}

describe("visitor-scoped calls", () => {
  it.each([
    ["/api/usage", (c: ApiClient) => usageQuery(c)],
    ["/api/settings/tier", (c: ApiClient) => tierQuery(c)],
    ["/api/chunks/{chunk_id}", (c: ApiClient) => articleQuery("fl-83-49", "a quote", c)],
  ])("%s sends the visitor cookie", async (path, query) => {
    const { client: fake, GET } = client();
    await run(query(fake));
    expect(GET).toHaveBeenCalledWith(path, expect.objectContaining({ credentials: "include" }));
  });
});
