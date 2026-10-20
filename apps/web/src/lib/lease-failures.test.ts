import { FAILURE_CODES, LeaseFailure } from "./lease-check";
import { failureCopy, showsOnForm } from "./lease-failures";

const now = new Date("2026-10-19T21:48:00Z");

describe("failureCopy", () => {
  it.each(FAILURE_CODES)("has words for %s that name the failure and say what to do", (code) => {
    const copy = failureCopy(new LeaseFailure(code, "server words"), now);
    expect(copy.title.length).toBeGreaterThan(0);
    expect(copy.lead.endsWith(".") || copy.lead.endsWith("?")).toBe(true);
    expect(copy.title).not.toMatch(/error|exception|failed to/i);
  });

  it("uses the ErrorState spec's words for an unreadable lease", () => {
    expect(failureCopy(new LeaseFailure("unreadable", "x"), now)).toMatchObject({
      title: "This lease couldn't be read",
      lead: "The file has no selectable text.",
      next: "choose-file",
    });
  });

  it("works out the times and limits in code: the reset, the wait, the size", () => {
    expect(failureCopy(new LeaseFailure("quota_reached", "x"), now).lead).toBe(
      "They reset at 00:00 UTC, in 2 h 12 min.",
    );
    expect(failureCopy(new LeaseFailure("busy", "x", 45), now).lead).toBe(
      "Try again in 45 seconds.",
    );
    expect(failureCopy(new LeaseFailure("busy", "x"), now).lead).toBe("Try again in 30 seconds.");
    expect(failureCopy(new LeaseFailure("too_large", "x"), now).lead).toBe(
      "Choose a file of 10 MB or less.",
    );
  });

  it("sends the reader to the right fix", () => {
    const next = (code: string) => failureCopy(new LeaseFailure(code, "x"), now).next;
    expect(next("jurisdiction_unknown")).toBe("choose-jurisdiction");
    expect(next("too_large")).toBe("choose-file");
    expect(next("timed_out")).toBe("retry");
    expect(next("quota_reached")).toBe("none");
  });

  it("keeps the server's message for a code it has no words for", () => {
    expect(failureCopy(new LeaseFailure("brand_new", "The checker is being moved."), now)).toEqual({
      title: "The lease check stopped",
      lead: "The checker is being moved.",
      body: "Try again; if it keeps failing, quote the error ID below.",
      next: "retry",
    });
  });
});

describe("showsOnForm", () => {
  it("is true for the demo's own limits and a missing jurisdiction, not for a broken check", () => {
    expect(showsOnForm(new LeaseFailure("quota_reached", "x"))).toBe(true);
    expect(showsOnForm(new LeaseFailure("lease_checks_paused", "x"))).toBe(true);
    expect(showsOnForm(new LeaseFailure("jurisdiction_unknown", "x"))).toBe(true);
    expect(showsOnForm(new LeaseFailure("timed_out", "x"))).toBe(false);
  });
});
