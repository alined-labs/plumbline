import { render, screen } from "@testing-library/react";

import { UsageMeterView } from "./usage-meter";

const now = new Date("2026-10-19T21:48:00Z");
const reset = "2026-10-20T00:00:00Z";

describe("UsageMeterView", () => {
  it("is a meter with its value and maximum, the count and the reset time", () => {
    render(<UsageMeterView usage={{ used: 12, limit: 20, resets_at: reset }} now={now} />);
    const meter = screen.getByRole("meter", { name: "Demo questions used" });
    expect(meter).toHaveAttribute("aria-valuenow", "12");
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "20");
    expect(screen.getByText("12 of 20")).toBeInTheDocument();
    expect(screen.getByText("Resets at 00:00 UTC")).toBeInTheDocument();
    expect((meter.firstElementChild as HTMLElement).style.width).toBe("60%");
    expect(meter.firstElementChild).toHaveClass("bg-accent");
  });

  it("turns to a warning, in words as well as colour, from 80% used", () => {
    render(<UsageMeterView usage={{ used: 18, limit: 20, resets_at: reset }} now={now} />);
    const meter = screen.getByRole("meter");
    expect(meter.firstElementChild).toHaveClass("bg-warning");
    expect(screen.getByText("2 left today · resets at 00:00 UTC")).toHaveClass("text-warning");
  });

  it("says none are left when the allowance is spent", () => {
    render(<UsageMeterView usage={{ used: 20, limit: 20, resets_at: reset }} now={now} />);
    expect(screen.getByText("None left today · resets at 00:00 UTC")).toBeInTheDocument();
    expect(screen.getByText("20 of 20")).toBeInTheDocument();
  });
});
