import { isIndexed, parseUnindexed } from "./coverage";

describe("parseUnindexed", () => {
  it("reads a comma list of jurisdictions, in their fixed order, ignoring anything else", () => {
    expect(parseUnindexed("colombia, Dubai")).toEqual(["dubai", "colombia"]);
    expect(parseUnindexed("dubai,texas,")).toEqual(["dubai"]);
  });

  it("holds nothing back when unset or empty", () => {
    expect(parseUnindexed(undefined)).toEqual([]);
    expect(parseUnindexed("")).toEqual([]);
  });
});

describe("isIndexed", () => {
  it("is false only for a jurisdiction named as not indexed", () => {
    expect(isIndexed("dubai", ["dubai"])).toBe(false);
    expect(isIndexed("spain", ["dubai"])).toBe(true);
  });
});
