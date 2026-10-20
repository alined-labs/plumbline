import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { ConfirmDialog } from "./dialog";

function Harness({ onConfirm }: { onConfirm: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Upload
      </button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Before you upload a lease"
        confirm={{ label: "Upload a lease" }}
        onConfirm={() => {
          setOpen(false);
          onConfirm();
        }}
      >
        <p>Plumbline removes names from the lease before any model reads it.</p>
        <p>The check is legal information, not legal advice.</p>
      </ConfirmDialog>
    </>
  );
}

describe("ConfirmDialog", () => {
  it("opens on the safe choice, confirms, and returns focus to its trigger", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<Harness onConfirm={onConfirm} />);
    const trigger = screen.getByRole("button", { name: "Upload" });
    await user.click(trigger);

    const dialog = await screen.findByRole("dialog", { name: "Before you upload a lease" });
    expect(dialog).toHaveTextContent("legal information, not legal advice");
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Upload a lease" }));
    expect(onConfirm).toHaveBeenCalledOnce();
    await vi.waitFor(() => expect(trigger).toHaveFocus());
  });

  it("closes on Escape without confirming", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<Harness onConfirm={onConfirm} />);
    await user.click(screen.getByRole("button", { name: "Upload" }));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
