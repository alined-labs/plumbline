import { WAIVER } from "@/test/lease";

import { apiUrl } from "./api";
import { leaseEvents, LeaseFailure, startLeaseCheck, type LeaseEvent } from "./lease-check";

type Frame = { event: string; data: unknown; id?: string };

/** An event stream as the server writes it. */
function frames(...list: Frame[]): string {
  return list
    .map(
      ({ event, data, id }) =>
        `${id === undefined ? "" : `id: ${id}\n`}event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
    )
    .join("");
}

const stream = (body: string) =>
  new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });

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

async function collect(events: AsyncGenerator<LeaseEvent>): Promise<LeaseEvent[]> {
  const all: LeaseEvent[] = [];
  for await (const event of events) all.push(event);
  return all;
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
    const request = { file: lease, jurisdiction: "", signedOn: "" } as const;
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

const done = { event: "done", data: { findings: 0, language: "en" } } satisfies Frame;

describe("leaseEvents", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("yields the stages and findings in order, and stops at done", async () => {
    const send = fetchOf(
      stream(
        frames(
          { event: "stage", data: { stage: "uploaded" } },
          { event: "stage", data: { stage: "checking", done: 0, total: 2 } },
          { event: "finding", data: WAIVER },
          { event: "stage", data: { stage: "checking", done: 1, total: 2 } },
          { event: "done", data: { findings: 1, language: "en" } },
        ),
      ),
    );
    expect(await collect(leaseEvents("job-1", { fetch: send }))).toEqual([
      { type: "stage", stage: "uploaded" },
      { type: "stage", stage: "checking", done: 0, total: 2 },
      { type: "finding", finding: WAIVER },
      { type: "stage", stage: "checking", done: 1, total: 2 },
      { type: "done", findings: 1, language: "en" },
    ]);
    const [url, init] = send.mock.calls[0] ?? [];
    expect(url).toBe(apiUrl("/api/check-lease/job-1/events"));
    const headers = new Headers(init?.headers);
    expect(headers.get("Accept")).toBe("text/event-stream");
    expect(headers.has("Last-Event-ID")).toBe(false);
  });

  it("reads the API's own bytes, where a count it does not have is null", async () => {
    // As Lane D's route writes them (LeaseStageEvent.model_dump_json): every field, null or not.
    const send = fetchOf(
      stream(
        'id: 1\nevent: stage\ndata: {"stage":"uploaded","done":null,"total":null}\n\n' +
          'id: 2\nevent: stage\ndata: {"stage":"checking","done":0,"total":3}\n\n' +
          'id: 3\nevent: done\ndata: {"findings":0,"language":"en"}\n\n',
      ),
    );
    expect(await collect(leaseEvents("job-1", { fetch: send }))).toEqual([
      { type: "stage", stage: "uploaded" },
      { type: "stage", stage: "checking", done: 0, total: 3 },
      { type: "done", findings: 0, language: "en" },
    ]);
  });

  it("ignores events that are not its own", async () => {
    const send = fetchOf(stream(`: keep-alive\n\nevent: ping\ndata: {}\n\n${frames(done)}`));
    expect(await collect(leaseEvents("job-1", { fetch: send }))).toEqual([
      { type: "done", findings: 0, language: "en" },
    ]);
  });

  it("throws what the stream says failed, after the events before it", async () => {
    const send = fetchOf(
      stream(
        frames(
          { event: "stage", data: { stage: "reading" } },
          {
            event: "failed",
            data: { code: "no_clauses", message: "We couldn't find numbered clauses." },
          },
        ),
      ),
    );
    const seen: LeaseEvent[] = [];
    const failure = await failureOf(
      (async () => {
        for await (const event of leaseEvents("job-1", { fetch: send })) seen.push(event);
      })(),
    );
    expect(failure).toMatchObject({
      code: "no_clauses",
      message: "We couldn't find numbered clauses.",
    });
    expect(seen).toEqual([{ type: "stage", stage: "reading" }]);
  });

  it("fails on a finding that does not match the schema instead of dropping it", async () => {
    const send = fetchOf(
      stream(frames({ event: "finding", data: { ...WAIVER, severity: "urgent" } })),
    );
    const failure = await failureOf(collect(leaseEvents("job-1", { fetch: send })));
    expect(failure.code).toBe("unavailable");
  });

  it("reads the code of a refusal of the events route", async () => {
    const send = fetchOf(problem(404, { code: "not_found", detail: "No such check." }));
    const failure = await failureOf(collect(leaseEvents("gone", { fetch: send })));
    expect(failure).toMatchObject({ code: "not_found", message: "No such check." });
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("ends a stream with no event IDs that stops early as a lost connection", async () => {
    const send = fetchOf(stream(frames({ event: "stage", data: { stage: "reading" } })));
    const failure = await failureOf(collect(leaseEvents("job-1", { fetch: send })));
    expect(failure.code).toBe("connection_lost");
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("picks up a dropped stream from the last event ID", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const send = fetchOf(
      stream(frames({ event: "stage", data: { stage: "reading" }, id: "1" })),
      new TypeError("Failed to fetch"),
      stream(frames({ ...done, id: "2" })),
    );
    const seen = collect(leaseEvents("job-1", { fetch: send }));
    await vi.runAllTimersAsync();
    expect(await seen).toEqual([
      { type: "stage", stage: "reading" },
      { type: "done", findings: 0, language: "en" },
    ]);
    expect(send).toHaveBeenCalledTimes(3);
    expect(new Headers(send.mock.calls[1]?.[1]?.headers).get("Last-Event-ID")).toBe("1");
    expect(new Headers(send.mock.calls[2]?.[1]?.headers).get("Last-Event-ID")).toBe("1");
  });

  it("gives up when the stream keeps dropping without moving on", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const send = fetchOf(
      stream(frames({ event: "stage", data: { stage: "reading" }, id: "1" })),
      stream(""),
      stream(""),
      stream(""),
    );
    const outcome = failureOf(collect(leaseEvents("job-1", { fetch: send })));
    await vi.runAllTimersAsync();
    expect((await outcome).code).toBe("connection_lost");
    expect(send).toHaveBeenCalledTimes(4);
  });

  it("does not pick up a cancelled stream", async () => {
    const cancel = new AbortController();
    cancel.abort();
    const send = fetchOf(new DOMException("aborted", "AbortError"));
    await expect(
      collect(leaseEvents("job-1", { fetch: send, signal: cancel.signal })),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(send).toHaveBeenCalledTimes(1);
  });
});
