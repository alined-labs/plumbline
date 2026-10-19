import { lawsByJurisdiction } from "./laws";

const source = {
  id: "fl-stat-83-2026",
  law: "fl-stat-83",
  title: "Florida Statutes, Chapter 83, Part II",
  jurisdiction: "florida",
  language: "en",
  url: "https://example.org/83",
  edition: "2026",
  consolidated_on: null,
  retrieved_on: "2026-10-01",
  sha256: "0".repeat(64),
  format: "html",
  license_basis: "Public domain",
  committed: true,
  path: "data/corpus/raw/fl-stat-83-2026.html",
};

describe("lawsByJurisdiction", () => {
  it("lists every jurisdiction in order, with no laws while the corpus is empty", () => {
    const groups = lawsByJurisdiction({ version: 1, sources: [] });
    expect(groups.map((g) => g.code)).toEqual(["AE-DU", "ES", "CO", "US-FL"]);
    expect(groups.every((g) => g.laws.length === 0)).toBe(true);
  });

  it("dates a law by its consolidation, else by its retrieval", () => {
    const groups = lawsByJurisdiction({
      version: 1,
      sources: [
        source,
        {
          ...source,
          id: "es-lau-boe",
          title: "Ley 29/1994",
          jurisdiction: "spain",
          consolidated_on: "2025-03-26",
        },
      ],
    });
    expect(groups[1]?.laws).toEqual([
      { id: "es-lau-boe", title: "Ley 29/1994", edition: "2026", updatedOn: "2025-03-26" },
    ]);
    expect(groups[3]?.laws[0]?.updatedOn).toBe("2026-10-01");
  });

  it("reads the committed manifest", () => {
    expect(lawsByJurisdiction()).toHaveLength(4);
  });
});
