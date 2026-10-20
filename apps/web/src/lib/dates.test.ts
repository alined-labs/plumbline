import { formatClock, formatDate, formatDateTime, untilUtcMidnight } from "./dates";

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

  it("counts the time left until the demo resets at 00:00 UTC", () => {
    expect(untilUtcMidnight(new Date("2026-10-19T20:48:00Z"))).toBe("3 h 12 min");
    expect(untilUtcMidnight(new Date("2026-10-19T23:15:30Z"))).toBe("45 min");
    expect(untilUtcMidnight(new Date("2026-10-19T23:59:59Z"))).toBe("1 min");
  });

  it("writes the time of day a reset happens, in UTC", () => {
    expect(formatClock("2026-10-20T00:00:00Z")).toBe("00:00 UTC");
    expect(formatClock(new Date("2026-10-20T09:05:00Z"))).toBe("09:05 UTC");
  });
});
