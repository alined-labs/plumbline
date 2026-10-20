import { feedbackBody } from "./feedback";

describe("feedbackBody", () => {
  it("sends only the verdict for a helpful answer", () => {
    expect(feedbackBody("req_1", { helpful: true })).toEqual({
      request_id: "req_1",
      helpful: true,
    });
  });

  it("sends the reasons in the spec's order and a trimmed note, or none", () => {
    const reasons = new Set(["outdated_law", "wrong_citation"] as const);
    expect(
      feedbackBody("req_1", { helpful: false, reasons, note: "  It cites the old act.  " }),
    ).toEqual({
      request_id: "req_1",
      helpful: false,
      reasons: ["wrong_citation", "outdated_law"],
      note: "It cites the old act.",
    });
    expect(feedbackBody("req_1", { helpful: false, reasons: new Set(), note: "   " })).toEqual({
      request_id: "req_1",
      helpful: false,
      reasons: [],
      note: null,
    });
  });
});
