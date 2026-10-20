import { spanRange, splitAtSpan } from "./article";

describe("splitAtSpan", () => {
  it("cuts the text before, at and after the span", () => {
    expect(splitAtSpan("The landlord shall return the deposit.", { start: 4, end: 12 })).toEqual({
      before: "The ",
      cited: "landlord",
      after: " shall return the deposit.",
    });
  });

  it("counts code points, as the API does, so an astral character does not shift the span", () => {
    // "😀" is two UTF-16 units but one code point.
    expect(splitAtSpan("😀 la fianza", { start: 2, end: 4 })).toEqual({
      before: "😀 ",
      cited: "la",
      after: " fianza",
    });
  });

  it("gives nothing when there is no span or it does not fit", () => {
    expect(splitAtSpan("abc", null)).toBeNull();
    expect(splitAtSpan("abc", { start: 2, end: 2 })).toBeNull();
    expect(splitAtSpan("abc", { start: 1, end: 9 })).toBeNull();
    expect(splitAtSpan("abc", { start: -1, end: 2 })).toBeNull();
  });
});

describe("spanRange", () => {
  it("says where the quote sits, counting from 1, with the thousands separated", () => {
    expect(spanRange("x".repeat(2340), { start: 1203, end: 1330 })).toBe(
      "Characters 1,204 to 1,330 of 2,340",
    );
  });
});
