import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ToastProvider, useToasts, type ToastHandle } from "./toast";

let handle: ToastHandle | undefined;

function Buttons({ onView }: { onView: () => void }) {
  const toasts = useToasts();
  return (
    <>
      <button type="button" onClick={() => toasts.confirm("Reference copied")}>
        Copy
      </button>
      <button
        type="button"
        onClick={() =>
          toasts.confirm("Lease checked: 4 findings", { label: "View", onClick: onView })
        }
      >
        Finish
      </button>
      <button
        type="button"
        onClick={() => (handle = toasts.job("Checking lease · 8 of 14 clauses"))}
      >
        Start
      </button>
    </>
  );
}

function setup(onView = vi.fn()) {
  render(
    <ToastProvider>
      <Buttons onView={onView} />
    </ToastProvider>,
  );
  return { onView, user: userEvent.setup() };
}

describe("toasts", () => {
  afterEach(() => {
    vi.useRealTimers();
    handle = undefined;
  });

  it("confirms an action in one line, and leaves after four seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Copy" }));
    expect(await screen.findByText("Reference copied")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(4500));
    await vi.waitFor(() => expect(screen.queryByText("Reference copied")).not.toBeInTheDocument());
  });

  it("offers one action, and runs it", async () => {
    const { user, onView } = setup();
    await user.click(screen.getByRole("button", { name: "Finish" }));
    await user.click(await screen.findByRole("button", { name: "View" }));
    expect(onView).toHaveBeenCalledOnce();
  });

  it("keeps a job until it is updated, then lets the finished line go", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Start" }));
    expect(await screen.findByText("Checking lease · 8 of 14 clauses")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(screen.getByText("Checking lease · 8 of 14 clauses")).toBeInTheDocument();

    act(() => handle?.update({ label: "Lease checked: 4 findings", done: true }));
    expect(await screen.findByText("Lease checked: 4 findings")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(4500));
    await vi.waitFor(() =>
      expect(screen.queryByText("Lease checked: 4 findings")).not.toBeInTheDocument(),
    );
  });
});
