import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { markNoticeSeen } from "@/lib/lease-notice";
import { WAIVER } from "@/test/lease";

import { LeaseCheck } from "./lease-check";
import { LeaseJobProvider } from "./lease-job";

/** An event stream the test writes to as the checker would, one numbered event at a time. */
function liveEvents() {
  const encoder = new TextEncoder();
  let controller: ReadableStreamDefaultController<Uint8Array> | undefined;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  let id = 0;
  return {
    response: () =>
      new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    send(event: string, data: unknown) {
      id += 1;
      controller?.enqueue(
        encoder.encode(`id: ${id}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`),
      );
    },
  };
}

const accepted = () => new Response(JSON.stringify({ id: "job-1" }), { status: 202 });
const refused = (status: number, body: object) => () =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });

function setup(answers: (() => Response)[], { noticeSeen = true } = {}) {
  window.sessionStorage.clear();
  if (noticeSeen) markNoticeSeen();
  const queue = [...answers];
  const send = vi.fn<typeof fetch>(async () => {
    const next = queue.shift();
    if (!next) throw new Error("unexpected request");
    return next();
  });
  render(
    <LeaseJobProvider transport={{ fetch: send }}>
      <LeaseCheck />
    </LeaseJobProvider>,
  );
  return { send, user: userEvent.setup() };
}

/** Choose the lease the way a reader can without a picker: drop it on the zone. */
async function submit(user: ReturnType<typeof userEvent.setup>) {
  const lease = new File([new Uint8Array(1_468_006)], "contrato.pdf", { type: "application/pdf" });
  const zone = screen.getByRole("button", { name: /Drop a lease here or choose a file/ });
  fireEvent.drop(zone, { dataTransfer: { files: [lease] } });
  await user.click(await screen.findByRole("button", { name: "Check lease" }));
}

describe("LeaseCheck", () => {
  it("shows the redaction notice before the first upload only, and sends nothing until agreed", async () => {
    const first = liveEvents();
    const { send, user } = setup([accepted, first.response, accepted, liveEvents().response], {
      noticeSeen: false,
    });
    await submit(user);
    const dialog = await screen.findByRole("dialog", { name: "Before you upload a lease" });
    expect(dialog).toHaveTextContent("before any model reads it");
    expect(send).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Upload a lease" }));
    const heading = await screen.findByRole("heading", { name: "Checking your lease" });
    expect(heading).toHaveFocus();
    first.send("done", { findings: 0, language: "en" });
    await user.click(await screen.findByRole("button", { name: "Check another lease" }));

    await submit(user);
    expect(await screen.findByRole("heading", { name: "Checking your lease" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("sends nothing when the notice is cancelled, and keeps the chosen file", async () => {
    const { send, user } = setup([], { noticeSeen: false });
    await submit(user);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(send).not.toHaveBeenCalled();
    expect(await screen.findByText("contrato.pdf")).toBeInTheDocument();
  });

  it("shows the steps and the findings as they arrive, then the findings with the disclaimer", async () => {
    const live = liveEvents();
    const { user } = setup([accepted, live.response]);
    await submit(user);
    expect(await screen.findByRole("heading", { name: "Checking your lease" })).toBeInTheDocument();
    expect(screen.getByText("Findings appear here as each clause is checked.")).toBeInTheDocument();

    live.send("stage", { stage: "checking", done: 0, total: 2 });
    live.send("finding", WAIVER);
    expect(
      await screen.findByRole("heading", { name: /^Conflicts with the law/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent(
      "Checking clauses · 0 of 2",
    );

    live.send("stage", { stage: "checking", done: 2, total: 2 });
    live.send("done", { findings: 1, language: "en" });
    expect(await screen.findByRole("heading", { level: 2, name: "Findings" })).toBeInTheDocument();
    expect(
      screen.getByText("Lease checked: 1 finding. 1 conflicts with the law."),
    ).toBeInTheDocument();
  });

  it("does not call a lease with no findings lawful", async () => {
    const live = liveEvents();
    const { user } = setup([accepted, live.response]);
    await submit(user);
    live.send("done", { findings: 0, language: "en" });
    expect(await screen.findByText("No findings.")).toBeInTheDocument();
    expect(screen.getByText(/not a clean bill of health/)).toBeInTheDocument();
  });

  it("goes back to the form on Cancel", async () => {
    const { user } = setup([accepted, liveEvents().response]);
    await submit(user);
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    const zone = await screen.findByRole("button", { name: /Drop a lease here or choose a file/ });
    // The button that was pressed is gone: the focus goes to the form's first control.
    expect(zone).toHaveFocus();
  });

  it("words a failure with no findings as the whole view, and offers the way on", async () => {
    const { user } = setup([refused(422, { code: "unreadable", detail: "No text layer." })]);
    await submit(user);
    const heading = await screen.findByRole("heading", {
      level: 2,
      name: "This lease couldn't be read",
    });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText("The file has no selectable text.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Choose another file" }));
    const zone = await screen.findByRole("button", { name: /Drop a lease here or choose a file/ });
    expect(zone).toHaveFocus();
  });

  it("keeps the findings it has when the check stops part way, and tries again", async () => {
    const live = liveEvents();
    const { send, user } = setup([accepted, live.response, accepted, liveEvents().response]);
    await submit(user);
    live.send("finding", WAIVER);
    live.send("failed", { code: "timed_out", message: "Too slow." });
    expect(await screen.findByRole("heading", { name: "Findings so far" })).toBeInTheDocument();
    expect(screen.getByText("The check stopped.")).toBeInTheDocument();
    expect(screen.getByText(WAIVER.title)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Checking your lease" })).toBeInTheDocument();
    expect(send).toHaveBeenCalledTimes(4);
  });

  it("sends the reader back to the form, with the file, when the jurisdiction is missing", async () => {
    const live = liveEvents();
    const { user } = setup([accepted, live.response]);
    await submit(user);
    live.send("failed", { code: "jurisdiction_unknown", message: "Which law?" });
    expect(await screen.findByText("Which law governs this lease?")).toBeInTheDocument();
    expect(screen.getByText("Choose where the property is.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("contrato.pdf")).toBeInTheDocument();
    expect(screen.getByLabelText("Where is the property?")).toHaveFocus();
  });

  it("says the demo's checks are used up and keeps the form", async () => {
    const { user } = setup([refused(429, { code: "quota_reached", detail: "Slow down." })]);
    await submit(user);
    expect(await screen.findByText("Today's demo checks are used up.")).toBeInTheDocument();
    expect(screen.getByText(/They reset at 00:00 UTC, in/)).toBeInTheDocument();
    expect(screen.getByText("contrato.pdf")).toBeInTheDocument();
    // With a file already chosen, the focus lands on the button that sends it.
    expect(screen.getByRole("button", { name: "Check lease" })).toHaveFocus();
  });
});
