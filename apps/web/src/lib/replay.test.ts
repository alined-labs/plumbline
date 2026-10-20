import path from "node:path";

import { answerAsText, answerView } from "./answer";
import { isWithheld, toMessages } from "./replay";
import { loadReplay } from "./replay-files";

const FIXTURES = path.join(process.cwd(), "src/test/fixtures/evals");
const replay = loadReplay(FIXTURES);
const item = (id: string) => {
  const found = replay.items.find((candidate) => candidate.item_id === id);
  if (!found) throw new Error(`no ${id} in the fixture`);
  return found;
};

describe("loadReplay", () => {
  it("reads the default configuration's stored answers, checked line by line", () => {
    expect(replay.config).toBe("A2");
    expect(replay.config_hash).toBe(`${"0".repeat(63)}1`);
    expect(replay.items.map((stored) => stored.item_id)).toEqual([
      "fl-0003",
      "co-0004",
      "oos-0002",
    ]);
  });

  it("is empty before any answers are stored", () => {
    expect(loadReplay(path.join(FIXTURES, "results"))).toEqual({
      config: null,
      config_hash: null,
      items: [],
    });
  });
});

describe("toMessages", () => {
  it("turns a stored answer into the question and the answer a live stream leaves", () => {
    const [question, answer] = toMessages(item("fl-0003"), "A2", "abc");
    expect(question?.role).toBe("user");
    expect(question?.parts).toEqual([
      { type: "text", text: "How long does my landlord have to return my deposit in Florida?" },
    ]);
    const view = answerView(answer!);
    expect(view.citations.map((citation) => citation.label)).toEqual(["Fla. Stat. § 83.49(3)(a)"]);
    expect(view.markdown).toContain("[1](#source-1)");
    expect(view.summary?.status).toBe("answered");
    // No request id: the answer offers no feedback.
    expect(view.trace).toMatchObject({ request_id: "", tier: "static", config_name: "A2" });
  });

  it("keeps an abstention's reason", () => {
    const [, answer] = toMessages(item("oos-0002"), "A2", "abc");
    expect(answerView(answer!).summary).toMatchObject({
      status: "abstained",
      abstain_reason: expect.stringContaining("residential tenancy law"),
    });
  });
});

describe("a withheld quote", () => {
  it("is recognised by Lane B's marker", () => {
    expect(isWithheld(item("co-0004").answer.citations[0]!.quote)).toBe(true);
    expect(isWithheld("the landlord shall have 15 days")).toBe(false);
  });

  it("is copied as a pointer to the official text, never as the marker", () => {
    const [, answer] = toMessages(item("co-0004"), "A2", "abc");
    const text = answerAsText(answerView(answer!));
    expect(text).toContain("[1] Ley 820 de 2003, art. 16 (passage not republished here");
    expect(text).not.toContain("[Withheld");
  });
});
