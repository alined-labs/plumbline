import { usageView } from "./usage";

const now = new Date("2026-10-19T21:48:00Z");
const reset = "2026-10-20T00:00:00Z";

describe("usageView", () => {
  it("counts the day's questions and says when they reset", () => {
    expect(usageView({ used: 12, limit: 20, resets_at: reset }, now)).toMatchObject({
      count: "12 of 20",
      share: 0.6,
      low: false,
      exhausted: false,
      note: "Resets at 00:00 UTC",
    });
  });

  it("turns low from 80% used and says how many are left", () => {
    expect(usageView({ used: 16, limit: 20, resets_at: reset }, now)).toMatchObject({
      low: true,
      left: 4,
      note: "4 left today · resets at 00:00 UTC",
    });
    expect(usageView({ used: 15, limit: 20, resets_at: reset }, now).low).toBe(false);
  });

  it("is spent at the limit, with the composer's words naming the wait", () => {
    expect(usageView({ used: 20, limit: 20, resets_at: reset }, now)).toMatchObject({
      exhausted: true,
      note: "None left today · resets at 00:00 UTC",
      composerReason: "Demo questions reset at 00:00 UTC, in 2 h 12 min.",
    });
  });

  it("never reads past the limit", () => {
    expect(usageView({ used: 23, limit: 20, resets_at: reset }, now)).toMatchObject({
      used: 20,
      count: "20 of 20",
      exhausted: true,
    });
  });
});
