import { apiUrl } from "./api";
import { LeaseFailure, startLeaseCheck } from "./lease-check";

const problem = (status: number, body: object, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/problem+json", ...headers },
  });

/** A fetch that answers with the given responses, one per call, and remembers the calls. */
function fetchOf(...answers: (Response | Error | DOMException)[]) {
  const queue = [...answers];
  return vi.fn<typeof fetch>(async () => {
    const next = queue.shift();
    if (!next) throw new Error("fetch was called more often than the test expected");
    // A DOMException from jsdom is not an instance of this realm's Error, so test for a Response.
    if (next instanceof Response) return next;
    throw next;
  });
}

async function failureOf(run: Promise<unknown>): Promise<LeaseFailure> {
  const error = await run.then(
    () => undefined,
    (thrown: unknown) => thrown,
  );
  if (!(error instanceof LeaseFailure)) throw new Error("expected a LeaseFailure");
  return error;
}

const lease = new File([new Uint8Array(10)], "lease.pdf", { type: "application/pdf" });

describe("startLeaseCheck", () => {
  it("sends the lease itself as the body, with the optional fields in the query", async () => {
    const send = fetchOf(new Response(JSON.stringify({ id: "job-1" }), { status: 202 }));
    const id = await startLeaseCheck(
      { file: lease, jurisdiction: "spain", signedOn: "2025-03-01" },
      { fetch: send },
    );
    expect(id).toBe("job-1");
    const [url, init] = send.mock.calls[0] ?? [];
    expect(url).toBe(`${apiUrl("/api/check-lease")}?jurisdiction=spain&signed_on=2025-03-01`);
    expect(init).toMatchObject({ method: "POST", body: lease, credentials: "include" });
  });

  it("leaves out the fields the reader left empty", async () => {
    const send = fetchOf(new Response(JSON.stringify({ id: "job-1" }), { status: 202 }));
    await startLeaseCheck({ file: lease, jurisdiction: "", signedOn: "" }, { fetch: send });
    expect(send.mock.calls[0]?.[0]).toBe(apiUrl("/api/check-lease"));
  });

  it("names a refusal by the code in its problem, in the server's words", async () => {
    const send = fetchOf(
      problem(413, { code: "too_large", title: "Too large", detail: "The limit is 10 MB." }),
    );
    const failure = await failureOf(
      startLeaseCheck({ file: lease, jurisdiction: "", signedOn: "" }, { fetch: send }),
    );
    expect(failure).toMatchObject({ code: "too_large", message: "The limit is 10 MB." });
  });

  it("falls back to the status when the body names no code, and reads Retry-After", async () => {
    const send = fetchOf(
      new Response("<html>nope</html>", { status: 415 }),
      problem(429, { title: "Too many requests" }, { "Retry-After": "120" }),
    );
    const request = { file: lease, jurisdiction: "", signedOn: "" };
    expect(await failureOf(startLeaseCheck(request, { fetch: send }))).toMatchObject({
      code: "unsupported_type",
    });
    expect(await failureOf(startLeaseCheck(request, { fetch: send }))).toMatchObject({
      code: "quota_reached",
      retryAfter: 120,
    });
  });

  it("says the checker did not answer when the network fails", async () => {
    const send = fetchOf(new TypeError("Failed to fetch"));
    const failure = await failureOf(
      startLeaseCheck({ file: lease, jurisdiction: "", signedOn: "" }, { fetch: send }),
    );
    expect(failure.code).toBe("unavailable");
  });

  it("lets a cancel through as the abort it is", async () => {
    const cancel = new AbortController();
    cancel.abort();
    const send = fetchOf(new DOMException("aborted", "AbortError"));
    await expect(
      startLeaseCheck(
        { file: lease, jurisdiction: "", signedOn: "" },
        { fetch: send, signal: cancel.signal },
      ),
    ).rejects.toMatchObject({ name: "AbortError" });
  });
});
