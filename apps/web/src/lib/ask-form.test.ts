import { askBody, askSchema, EMPTY_ASK, MAX_QUESTION_CHARS } from "./ask-form";

describe("askSchema", () => {
  it("accepts a question with no filter and no date", () => {
    expect(askSchema.parse({ ...EMPTY_ASK, question: "  How long?  " })).toEqual({
      question: "How long?",
      jurisdictions: [],
      asOf: "",
    });
  });

  it("explains how to fix a long question or a bad date", () => {
    const result = askSchema.safeParse({
      question: "x".repeat(MAX_QUESTION_CHARS + 1),
      jurisdictions: ["florida"],
      asOf: "2024-02-30",
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues.map((issue) => issue.message)).toEqual([
      "Shorten the question to 2000 characters or fewer",
      "Enter the date as day, month and year",
    ]);
  });

  it("rejects a jurisdiction the API does not hold", () => {
    expect(
      askSchema.safeParse({ ...EMPTY_ASK, question: "Q", jurisdictions: ["texas"] }).success,
    ).toBe(false);
  });
});

describe("askBody", () => {
  it("sends the filter and the as-of date the way the API reads them", () => {
    expect(askBody({ question: "Q", jurisdictions: [], asOf: "" })).toEqual({
      as_of: null,
      jurisdictions: [],
    });
    expect(askBody({ question: "Q", jurisdictions: ["spain"], asOf: "2024-03-01" })).toEqual({
      as_of: "2024-03-01",
      jurisdictions: ["spain"],
    });
  });
});
