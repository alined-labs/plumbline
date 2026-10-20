import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { WAIVER } from "@/test/lease";

import { LeaseJobProvider, useLeaseJob } from "./lease-job";

const lease = new File([new Uint8Array(10)], "lease.pdf", { type: "application/pdf" });

function Probe() {
  const { job, start, retry, reset } = useLeaseJob();
  return (
    <>
      <p data-testid="status">{job.status}</p>
      <p data-testid="findings">{job.status === "idle" ? 0 : job.findings.length}</p>
      <p data-testid="failure">{job.status === "failed" ? job.failure.code : ""}</p>
      <button onClick={() => start({ file: lease, jurisdiction: "florida", signedOn: "" })}>
        start
      </button>
      <button onClick={retry}>retry</button>
      <button onClick={reset}>reset</button>
    </>
  );
}

const events = (...frames: [string, unknown][]) =>
  frames.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("");
const accepted = () => new Response(JSON.stringify({ id: "job-1" }), { status: 202 });
const stream = (body: string) =>
  new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });

function setup(...answers: (Response | Promise<Response>)[]) {
  const queue = [...answers];
  const send = vi.fn<typeof fetch>(async () => {
    const next = queue.shift();
    if (!next) throw new Error("unexpected request");
    return next;
  });
  render(
    <LeaseJobProvider transport={{ fetch: send }}>
      <Probe />
    </LeaseJobProvider>,
  );
  return { send, user: userEvent.setup() };
}

describe("LeaseJobProvider", () => {
  it("runs a check from the upload to its last event", async () => {
    const { send, user } = setup(
      accepted(),
      stream(
        events(
          ["stage", { stage: "uploaded" }],
          ["finding", WAIVER],
          ["done", { findings: 1, language: "en" }],
        ),
      ),
    );
    expect(screen.getByTestId("status")).toHaveTextContent("idle");
    await user.click(screen.getByRole("button", { name: "start" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("done"));
    expect(screen.getByTestId("findings")).toHaveTextContent("1");
    expect(send.mock.calls.map(([url]) => String(url))).toEqual([
      expect.stringMatching(/\/api\/check-lease\?jurisdiction=florida$/),
      expect.stringMatching(/\/api\/check-lease\/job-1\/events$/),
    ]);
  });

  it("fails with the code the checker gave when the upload is refused", async () => {
    const { user } = setup(
      new Response(JSON.stringify({ code: "too_large", detail: "The limit is 10 MB." }), {
        status: 413,
        headers: { "Content-Type": "application/problem+json" },
      }),
    );
    await user.click(screen.getByRole("button", { name: "start" }));
    await waitFor(() => expect(screen.getByTestId("failure")).toHaveTextContent("too_large"));
  });

  it("tries the same request again", async () => {
    const { send, user } = setup(
      accepted(),
      stream(events(["failed", { code: "timed_out", message: "Too slow." }])),
      accepted(),
      stream(events(["done", { findings: 0, language: "en" }])),
    );
    await user.click(screen.getByRole("button", { name: "start" }));
    await waitFor(() => expect(screen.getByTestId("failure")).toHaveTextContent("timed_out"));
    await user.click(screen.getByRole("button", { name: "retry" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("done"));
    expect(send).toHaveBeenCalledTimes(4);
    expect(send.mock.calls[2]?.[1]?.body).toBe(lease);
  });

  it("goes back to the form on reset, and nothing more arrives from the check it left", async () => {
    // The events stream never ends: the check is still running when the reader leaves.
    const open = new Response(new ReadableStream({ start() {} }), { status: 200 });
    const { user } = setup(accepted(), open);
    await user.click(screen.getByRole("button", { name: "start" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("running"));
    await user.click(screen.getByRole("button", { name: "reset" }));
    expect(screen.getByTestId("status")).toHaveTextContent("idle");
  });
});
