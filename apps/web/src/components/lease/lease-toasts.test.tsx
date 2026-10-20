import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";

import { ToastProvider } from "@/components/ui/toast";
import { WAIVER } from "@/test/lease";

import { LeaseJobProvider, useLeaseJob } from "./lease-job";
import { LeaseToasts } from "./lease-toasts";

// The lease check's transport loads with a dynamic import on the first check. Loading it here
// first keeps its compile time out of each test's time limit, which a busy machine (the hub's)
// can otherwise exceed.
beforeAll(async () => {
  await import("@/lib/lease-check");
});

const nav = vi.hoisted(() => ({ pathname: "/", push: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: nav.push }),
}));

/** An event stream the test writes to as the checker would. */
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

function Starter() {
  const { start } = useLeaseJob();
  const lease = new File([new Uint8Array(10)], "lease.pdf", { type: "application/pdf" });
  return (
    <button onClick={() => start({ file: lease, jurisdiction: "", signedOn: "" })}>start</button>
  );
}

function setup(pathname: string) {
  nav.pathname = pathname;
  nav.push.mockClear();
  const live = liveEvents();
  const answers = [
    () => new Response(JSON.stringify({ id: "job-1" }), { status: 202 }),
    live.response,
  ];
  const send = vi.fn<typeof fetch>(async () => {
    const next = answers.shift();
    if (!next) throw new Error("unexpected request");
    return next();
  });
  const tree = (): ReactElement => (
    <ToastProvider>
      <LeaseJobProvider transport={{ fetch: send }}>
        <LeaseToasts />
        <Starter />
      </LeaseJobProvider>
    </ToastProvider>
  );
  const view = render(tree());
  return { live, user: userEvent.setup(), rerender: () => view.rerender(tree()) };
}

describe("LeaseToasts", () => {
  it("keeps a running check visible elsewhere as a toast with Cancel", async () => {
    const { live, user } = setup("/about/");
    await user.click(screen.getByRole("button", { name: "start" }));
    live.send("stage", { stage: "checking", done: 8, total: 14 });
    expect(await screen.findByText("Checking lease · 8 of 14 clauses")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByText(/^Checking lease/)).not.toBeInTheDocument());
  });

  it("says how the check ended, with a way back to it", async () => {
    const { live, user } = setup("/");
    await user.click(screen.getByRole("button", { name: "start" }));
    live.send("stage", { stage: "reading" });
    live.send("finding", WAIVER);
    live.send("done", { findings: 1, language: "en" });
    expect(await screen.findByText("Lease checked: 1 finding")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View" }));
    expect(nav.push).toHaveBeenCalledWith("/check-lease");
  });

  it("says so when the check stopped while the reader was away", async () => {
    const { live, user } = setup("/");
    await user.click(screen.getByRole("button", { name: "start" }));
    live.send("stage", { stage: "reading" });
    live.send("failed", { code: "timed_out", message: "Too slow." });
    expect(await screen.findByText("The lease check stopped")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View" })).toBeInTheDocument();
  });

  it("shows no toast on the lease page, where the page shows the check", async () => {
    const { live, user } = setup("/check-lease/");
    await user.click(screen.getByRole("button", { name: "start" }));
    live.send("stage", { stage: "checking", done: 1, total: 2 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(screen.queryByText(/^Checking lease/)).not.toBeInTheDocument();
  });

  it("lets the toast go when the reader comes back to the page", async () => {
    const { live, user, rerender } = setup("/");
    await user.click(screen.getByRole("button", { name: "start" }));
    live.send("stage", { stage: "checking", done: 1, total: 2 });
    expect(await screen.findByText("Checking lease · 1 of 2 clauses")).toBeInTheDocument();
    nav.pathname = "/check-lease/";
    rerender();
    await waitFor(() => expect(screen.queryByText(/^Checking lease/)).not.toBeInTheDocument());
  });
});
