import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MAX_LEASE_BYTES } from "@/lib/lease-upload";

import { UploadForm } from "./upload-form";

function file(name: string, type: string, size = 1000) {
  return new File([new Uint8Array(size)], name, { type });
}

function setup() {
  const onSubmit = vi.fn();
  render(<UploadForm onSubmit={onSubmit} />);
  const zone = screen.getByRole("button", { name: /Drop a lease here or choose a file/ });
  return { onSubmit, zone, user: userEvent.setup() };
}

/** The picker is hidden: dropping on the zone is how a test (and a reader) gives it a file. */
function drop(zone: HTMLElement, chosen: File) {
  fireEvent.drop(zone, { dataTransfer: { files: [chosen] } });
}

describe("UploadForm", () => {
  it("says how to fix a file of the wrong type before sending anything", async () => {
    const { zone, onSubmit } = setup();
    drop(zone, file("lease.txt", "text/plain"));
    const error = await screen.findByText("Upload a PDF or DOCX file");
    // The error is in the zone's description, so it is read when the zone is focused.
    await waitFor(() =>
      expect(zone.getAttribute("aria-describedby")?.split(" ")).toContain(error.id),
    );
    expect(zone).toHaveAttribute("data-invalid");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("refuses a file over 10 MB", async () => {
    const { zone } = setup();
    drop(zone, file("lease.pdf", "application/pdf", MAX_LEASE_BYTES + 1));
    expect(await screen.findByText("Choose a file of 10 MB or less")).toBeInTheDocument();
  });

  it("asks for a lease when none is chosen", async () => {
    const { user, onSubmit } = setup();
    await user.click(screen.getByRole("button", { name: "Check lease" }));
    expect(await screen.findByText("Choose a lease to check")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("shows the chosen file with its size, lets it be removed, and submits it with the filters", async () => {
    const { user, zone, onSubmit } = setup();
    const lease = file("contrato.pdf", "application/pdf", 1.4 * 1024 * 1024);
    drop(zone, lease);
    expect(await screen.findByText("contrato.pdf")).toBeInTheDocument();
    expect(screen.getByText("1.4 MB")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Where is the property?"), "spain");
    fireEvent.change(screen.getByLabelText("Date signed"), { target: { value: "2024-03-01" } });
    await user.click(screen.getByRole("button", { name: "Check lease" }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        { file: lease, jurisdiction: "spain", signedOn: "2024-03-01" },
        expect.anything(),
      ),
    );

    await user.click(screen.getByRole("button", { name: "Remove contrato.pdf" }));
    expect(
      await screen.findByRole("button", { name: /Drop a lease here or choose a file/ }),
    ).toBeInTheDocument();
  });

  it("explains the optional fields and takes neither", async () => {
    const { zone, user, onSubmit } = setup();
    expect(screen.getByLabelText("Where is the property?")).toHaveDisplayValue(
      "Detect from the lease",
    );
    expect(screen.getByLabelText("Date signed")).toHaveAccessibleDescription(/Optional/);
    drop(zone, file("lease.docx", "", 500));
    await user.click(await screen.findByRole("button", { name: "Check lease" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ jurisdiction: "", signedOn: "" });
  });

  it("describes the zone with the redaction promise and opens the picker from the keyboard", async () => {
    const { zone, user } = setup();
    const [helpId] = zone.getAttribute("aria-describedby")?.split(" ") ?? [];
    expect(document.getElementById(helpId ?? "")).toHaveTextContent(
      "Names, IDs and addresses are removed before any model reads it.",
    );
    const click = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {});
    zone.focus();
    await user.keyboard("{Enter}");
    expect(click).toHaveBeenCalledOnce();
    click.mockRestore();
  });
});
