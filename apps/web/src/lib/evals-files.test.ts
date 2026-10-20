import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { loadEvals } from "./evals-files";

const FIXTURES = path.join(process.cwd(), "src/test/fixtures/evals");

function tempDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), "evals-"));
}

describe("loadEvals", () => {
  it("reads every configuration's dev run in the plan's order, the judge table and thresholds", () => {
    const data = loadEvals(FIXTURES);
    expect(data.runs.map((run) => run.config_name)).toEqual(["A0", "A2", "LC"]);
    expect(data.agreement?.sets[0]?.labels).toBe("constructed");
    expect(data.thresholds).toEqual({
      "recall@5": 0.6,
      citation_precision: 0.7,
      abstention_accuracy: 0.6,
    });
  });

  it("finds nothing yet in a folder with no results", () => {
    expect(loadEvals(tempDir())).toEqual({ runs: [], agreement: null, thresholds: {} });
  });

  it("reads thresholds kept at the top level, and ignores what is not a number", () => {
    const dir = tempDir();
    fs.writeFileSync(
      path.join(dir, "baseline.json"),
      JSON.stringify({ "recall@5": 0.5, note: "why", unknown_metric: 1 }),
    );
    expect(loadEvals(dir).thresholds).toEqual({ "recall@5": 0.5 });
  });

  it("fails the build on a results file that does not fit, naming it", () => {
    const dir = tempDir();
    fs.mkdirSync(path.join(dir, "results", "A2"), { recursive: true });
    fs.writeFileSync(path.join(dir, "results", "A2", "dev.json"), JSON.stringify({ run_id: "x" }));
    expect(() => loadEvals(dir)).toThrow(/A2\/dev\.json does not fit/);
  });

  it("leaves the test split for the release", () => {
    const dir = tempDir();
    const a2 = fs.readFileSync(path.join(FIXTURES, "results", "A2", "dev.json"), "utf8");
    fs.mkdirSync(path.join(dir, "results", "A2"), { recursive: true });
    fs.writeFileSync(path.join(dir, "results", "A2", "test.json"), a2);
    expect(loadEvals(dir).runs).toEqual([]);
  });
});
