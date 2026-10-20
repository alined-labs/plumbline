import { askBody, checkAsk, EMPTY_ASK, isIsoDate, MAX_QUESTION_CHARS } from "./ask-form";
import type { AskValues } from "./ask-form";

function messages(values: AskValues): string[] {
  return Object.values(checkAsk(values).errors).map((error) => error.message ?? "");
}

describe("checkAsk", () => {
  it("accepts a question with no filter and no date, trimmed", () => {
    expect(checkAsk({ ...EMPTY_ASK, question: "  How long?  " })).toEqual({
      values: { question: "How long?", jurisdictions: [], asOf: "" },
      errors: {},
    });
  });

  it("asks for a question when there is only space", () => {
    expect(messages({ ...EMPTY_ASK, question: "   " })).toEqual(["Write a question to ask"]);
  });

  it("explains how to fix a long question or a bad date, in the form's order", () => {
    expect(
      messages({
        question: "x".repeat(MAX_QUESTION_CHARS + 1),
        jurisdictions: ["florida"],
        asOf: "2024-02-30",
      }),
    ).toEqual([
      "Shorten the question to 2000 characters or fewer",
      "Enter the date as day, month and year",
    ]);
  });

  it("counts the limit after trimming", () => {
    const question = ` ${"x".repeat(MAX_QUESTION_CHARS)} `;
    expect(checkAsk({ ...EMPTY_ASK, question }).errors).toEqual({});
  });

  it("rejects a jurisdiction the API does not hold", () => {
    const values = {
      ...EMPTY_ASK,
      question: "Q",
      jurisdictions: ["texas"],
    } as unknown as AskValues;
    expect(checkAsk(values).values).toEqual({});
  });
});

describe("isIsoDate", () => {
  it("takes only real calendar days in ISO form", () => {
    expect(isIsoDate("2024-02-29")).toBe(true);
    expect(isIsoDate("2023-02-29")).toBe(false);
    expect(isIsoDate("2024-13-01")).toBe(false);
    expect(isIsoDate("1/3/2024")).toBe(false);
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
