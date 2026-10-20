import { render, screen, within } from "@testing-library/react";

import { spansFromTrace } from "@/lib/trace";

import { TraceWaterfall } from "./trace-waterfall";

describe("TraceWaterfall", () => {
  it("names each stage with its duration and places its bar on the shared axis", () => {
    const { spans, total } = spansFromTrace({
      cached: false,
      timings_ms: { retrieve: 900, generate: 3300 },
    });
    render(<TraceWaterfall spans={spans} total={total} label="Time per stage" />);
    const rows = within(screen.getByRole("list", { name: "Time per stage" })).getAllByRole(
      "listitem",
    );
    expect(rows.map((row) => row.textContent)).toEqual([
      "Searching the statutes900 ms",
      "Writing the answer3.3 s",
    ]);
    const bar = rows[1]?.querySelector<HTMLElement>("[class*=absolute]");
    expect(bar?.style.left).toBe(`${(900 / 4200) * 100}%`);
    expect(bar?.style.width).toBe(`${(3300 / 4200) * 100}%`);
    expect(bar?.className).toContain("bg-chart-1");
  });

  it("outlines a replayed stage and says so in text", () => {
    const { spans, total } = spansFromTrace({ cached: true, timings_ms: { retrieve: 5 } });
    render(<TraceWaterfall spans={spans} total={total} label="Time per stage" />);
    const row = screen.getByRole("listitem");
    expect(row).toHaveTextContent("5 ms (replayed)");
    expect(row.querySelector("[class*=absolute]")?.className).toContain("border-chart-3");
  });
});
