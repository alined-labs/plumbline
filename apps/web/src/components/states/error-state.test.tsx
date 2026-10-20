import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ErrorState } from "./error-state";

const props = {
  title: "Plumbline couldn't reach the statutes",
  lead: "The search service didn't answer.",
  body: "Your question is kept; try again in a moment.",
  errorId: "7f3a9c21",
  at: new Date("2026-10-19T14:32:00Z"),
};

describe("ErrorState", () => {
  it("names the failure, leads with the fix and shows a quotable ID", () => {
    render(<ErrorState {...props} />);
    expect(screen.getByRole("alert")).toHaveTextContent(props.title);
    expect(screen.getByText(props.lead).tagName).toBe("STRONG");
    expect(screen.getByText("err 7f3a9c21 · 19 Oct 2026, 14:32 UTC")).toBeInTheDocument();
  });

  it("retries, and copies the ID with its time", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ErrorState {...props} onRetry={onRetry} />);
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Copy error ID" }));
    await expect(navigator.clipboard.readText()).resolves.toBe(
      "err 7f3a9c21 · 19 Oct 2026, 14:32 UTC",
    );
    expect(screen.getByRole("button", { name: "Error ID copied" })).toBeInTheDocument();
  });

  it("sits under a page's own h1 as an h2, and words its one action as asked", () => {
    render(
      <ErrorState {...props} headingLevel={2} retryLabel="Choose another file" onRetry={vi.fn()} />,
    );
    expect(screen.getByRole("heading", { level: 2, name: props.title })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose another file" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });
});
