import type { Citation } from "@plumbline/ts-client";
import type { UIMessageChunk } from "ai";

import { messageFrom, stubChunks } from "@/test/stream";

import { answerView, linkMarkers, sourceNumber } from "./answer";

function citation(n: number, verified = true): UIMessageChunk {
  const data: Citation = {
    n,
    chunk_id: `c-${n}`,
    ref: {
      jurisdiction: "florida",
      law: "fl-stat-83",
      article: `83.4${n}`,
      paragraph: null,
      edition: "2026",
    },
    label: `Fla. Stat. § 83.4${n}`,
    quote: "The landlord shall return the deposit.",
    gloss: null,
    language: "en",
    verified,
    page: null,
  };
  return { type: "data-citation", id: `citation-${n}`, data };
}

/** The stub's stream with its text replaced and citations 1 to 3 (2 unverified) added. */
function chunksWithText(text: string): UIMessageChunk[] {
  return stubChunks()
    .filter((chunk) => chunk.type !== "text-delta" && chunk.type !== "data-citation")
    .flatMap((chunk): UIMessageChunk[] =>
      chunk.type === "text-start"
        ? [chunk, { type: "text-delta", id: chunk.id, delta: text }]
        : chunk.type === "data-answer"
          ? [citation(3), citation(2, false), citation(1), chunk]
          : [chunk],
    );
}

describe("linkMarkers", () => {
  it("links verified markers and drops the others with their space", () => {
    expect(linkMarkers("Within 15 days [1]. Not [2]; see [1].", new Set([1]))).toBe(
      "Within 15 days [1](#source-1). Not; see [1](#source-1).",
    );
  });

  it("leaves Markdown links alone", () => {
    expect(linkMarkers("[1](https://example.org)", new Set([1]))).toBe("[1](https://example.org)");
  });
});

describe("sourceNumber", () => {
  it("reads only #source-n", () => {
    expect(sourceNumber("#source-12")).toBe(12);
    expect(sourceNumber("https://example.org/#source-1")).toBeNull();
    expect(sourceNumber(undefined)).toBeNull();
  });
});

describe("answerView", () => {
  it("reads the stub's answer, citation, summary and trace", async () => {
    const view = answerView(await messageFrom(stubChunks()));
    expect(view.markdown).toContain("seed [1](#source-1).");
    expect(view.citations.map((c) => c.label)).toEqual(["Stub Act, s. 1"]);
    expect(view.summary?.status).toBe("answered");
    expect(view.trace?.tier).toBe("full");
  });

  it("keeps verified citations only, in the order the answer cites them", async () => {
    const view = answerView(await messageFrom(chunksWithText("First [3], then [2], then [1].")));
    expect(view.citations.map((c) => c.n)).toEqual([3, 1]);
    expect(view.markdown).toBe("First [3](#source-3), then, then [1](#source-1).");
  });
});
