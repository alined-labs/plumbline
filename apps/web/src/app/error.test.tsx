import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import PageError from "./error";

describe("PageError", () => {
  it("shows the error state with a quotable ID and logs what failed", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const reset = vi.fn();
    const error = new Error("boom");
    render(<PageError error={error} reset={reset} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("This page couldn't load");
    expect(screen.getByText(/^err [0-9a-f]{8} · /)).toBeInTheDocument();
    expect(log).toHaveBeenCalledWith(expect.stringMatching(/^err [0-9a-f]{8}$/), error);

    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledOnce();
    log.mockRestore();
  });

  it("uses the server's digest when there is one", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const error = Object.assign(new Error("boom"), { digest: "1234567" });
    render(<PageError error={error} reset={() => {}} />);
    expect(screen.getByText(/^err 1234567 · /)).toBeInTheDocument();
    vi.restoreAllMocks();
  });
});
