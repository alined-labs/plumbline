import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jurisdictionInfo } from "@/lib/jurisdictions";
import type { SampleLease } from "@/lib/sample-leases";

import { SamplePicker } from "./sample-picker";

const leases: SampleLease[] = [
  {
    id: "dubai-lease-02",
    place: "Jumeirah Village Circle townhouse",
    title: "Residential Tenancy Contract",
    jurisdiction: jurisdictionInfo("dubai"),
    signedOn: "2026-03-01",
  },
  {
    id: "fl-lease-01",
    place: "Miami apartment",
    title: "Residential Lease for an Apartment",
    jurisdiction: jurisdictionInfo("florida"),
    signedOn: "2026-08-15",
  },
];

const LEASE_TEXT = "# Residential Lease for an Apartment\n\n- Lease id: fl-lease-01\n";

function fetcher(answer: Response | "offline") {
  return vi.fn(async () => {
    if (answer === "offline") throw new TypeError("Failed to fetch");
    return answer;
  }) as unknown as typeof fetch;
}

describe("SamplePicker", () => {
  it("says why uploads are off and lists each lease by its place, title and date", () => {
    render(<SamplePicker leases={leases} onSubmit={vi.fn()} />);
    expect(screen.getByText("Uploads are off for now.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Miami apartment/ })).toBeInTheDocument();
    expect(
      screen.getByText("Residential Lease for an Apartment · Signed on 15 Aug 2026"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Read\s*the Miami apartment lease/ })).toHaveAttribute(
      "href",
      "/leases/fl-lease-01.md",
    );
  });

  it("asks for a lease when none is chosen, and puts the focus on the list", async () => {
    const onSubmit = vi.fn();
    render(<SamplePicker leases={leases} onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole("button", { name: "Check this lease" }));
    expect(screen.getByText("Choose a lease to check", { selector: "p" })).toBeInTheDocument();
    expect(screen.getAllByRole("radio")[0]).toHaveFocus();
    expect(screen.getByRole("group")).toHaveAttribute("aria-invalid", "true");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("sends the chosen lease's own text with its jurisdiction and signing date", async () => {
    const onSubmit = vi.fn();
    const get = fetcher(new Response(LEASE_TEXT));
    render(<SamplePicker leases={leases} onSubmit={onSubmit} fetcher={get} />);
    await userEvent.click(screen.getByRole("radio", { name: /Miami apartment/ }));
    await userEvent.click(screen.getByRole("button", { name: "Check this lease" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    expect(get).toHaveBeenCalledWith("/leases/fl-lease-01.md");
    const [request] = onSubmit.mock.calls[0] as [
      { file: File; jurisdiction: string; signedOn: string },
    ];
    expect(request.jurisdiction).toBe("florida");
    expect(request.signedOn).toBe("2026-08-15");
    expect(request.file.name).toBe("fl-lease-01.md");
    expect(await request.file.text()).toBe(LEASE_TEXT);
  });

  it("says how to recover when the lease cannot be loaded", async () => {
    const onSubmit = vi.fn();
    render(<SamplePicker leases={leases} onSubmit={onSubmit} fetcher={fetcher("offline")} />);
    await userEvent.click(screen.getByRole("radio", { name: /Miami apartment/ }));
    await userEvent.click(screen.getByRole("button", { name: "Check this lease" }));
    expect(
      await screen.findByText(/The lease could not be loaded: check your connection/),
    ).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Check this lease" })).toBeEnabled();
  });

  it("comes back with the lease that was chosen, focused", () => {
    render(<SamplePicker leases={leases} onSubmit={vi.fn()} initial="fl-lease-01" focusOnMount />);
    const miami = screen.getByRole("radio", { name: /Miami apartment/ });
    expect(miami).toBeChecked();
    expect(miami).toHaveFocus();
  });
});
