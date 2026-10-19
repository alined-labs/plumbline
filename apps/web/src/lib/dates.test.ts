import { formatDate, formatDateTime } from "./dates";

describe("dates", () => {
  it("writes a calendar day the way the content rules do", () => {
    expect(formatDate("2026-10-19")).toBe("19 Oct 2026");
    expect(formatDate("2026-01-01")).toBe("1 Jan 2026");
  });

  it("keeps the UTC day whatever the visitor's time zone", () => {
    expect(formatDate(new Date("2026-10-19T23:59:00Z"))).toBe("19 Oct 2026");
  });

  it("writes a moment with its UTC time", () => {
    expect(formatDateTime(new Date("2026-10-19T14:32:09Z"))).toBe("19 Oct 2026, 14:32 UTC");
  });
});
