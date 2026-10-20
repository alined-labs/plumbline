import { finding, WAIVER } from "@/test/lease";

import { groupFindings, SEVERITY_INFO, shownCitations, summarize } from "./lease";
import { findingSchema } from "./lease-schema";

describe("findingSchema", () => {
  it("accepts a finding the way Lane C's checker words it", () => {
    expect(findingSchema.parse(WAIVER)).toEqual(WAIVER);
  });

  it("rejects what the contract forbids: no citation, a long title, a confidence over 1", () => {
    expect(findingSchema.safeParse({ ...WAIVER, citations: [] }).success).toBe(false);
    expect(findingSchema.safeParse({ ...WAIVER, title: "x".repeat(121) }).success).toBe(false);
    expect(findingSchema.safeParse({ ...WAIVER, confidence: 1.2 }).success).toBe(false);
    expect(findingSchema.safeParse({ ...WAIVER, severity: "score" }).success).toBe(false);
  });
});

describe("groupFindings", () => {
  it("orders the groups most pressing first and each group by clause", () => {
    const groups = groupFindings([
      finding({ n: 4, severity: "match" }),
      finding({ n: 3, severity: "conflict" }),
      finding({ n: 2, severity: "check" }),
      finding({ n: 1, severity: "conflict" }),
    ]);
    expect(groups.map((g) => [g.severity, g.findings.map((f) => f.n)])).toEqual([
      ["conflict", [1, 3]],
      ["check", [2]],
      ["match", [4]],
    ]);
  });

  it("leaves a finding out when none of its citations is verified", () => {
    const [citation] = WAIVER.citations;
    if (!citation) throw new Error("the fixture has a citation");
    const unsupported = finding({ citations: [{ ...citation, verified: false }] });
    expect(shownCitations(unsupported)).toEqual([]);
    expect(groupFindings([unsupported])).toEqual([]);
  });

  it("words each severity's summary to agree with its count", () => {
    expect(SEVERITY_INFO.conflict.summary(1)).toBe("conflicts with the law");
    expect(SEVERITY_INFO.conflict.summary(2)).toBe("conflict with the law");
    expect(SEVERITY_INFO.match.summary(1)).toBe("matches the law");
    expect(SEVERITY_INFO.match.summary(8)).toBe("match the law");
  });
});

describe("summarize", () => {
  it("counts what is shown in the groups' order, worded to agree with each count", () => {
    expect(
      summarize([
        finding({ n: 1, severity: "conflict" }),
        finding({ n: 2, severity: "check" }),
        finding({ n: 3, severity: "conflict" }),
      ]),
    ).toEqual({ total: 3, text: "2 conflict with the law, 1 worth checking" });
    expect(summarize([finding({ severity: "match" })])).toEqual({
      total: 1,
      text: "1 matches the law",
    });
  });

  it("does not count a finding that has no verified citation, and is empty with none", () => {
    const [citation] = WAIVER.citations;
    if (!citation) throw new Error("the fixture has a citation");
    expect(summarize([finding({ citations: [{ ...citation, verified: false }] })])).toEqual({
      total: 0,
      text: "",
    });
    expect(summarize([])).toEqual({ total: 0, text: "" });
  });
});
