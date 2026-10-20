import { addStatus, finishRun, seconds, startRun, stepLabel } from "./run";

describe("run", () => {
  it("times each stage from its status part to the next", () => {
    let run = startRun(1000, 4);
    run = addStatus(run, { stage: "detecting", detail: null }, 1000);
    run = addStatus(run, { stage: "retrieving", detail: null }, 1200);
    run = addStatus(run, { stage: "retrieving", detail: "40 passages" }, 1500);
    run = addStatus(run, { stage: "generating", detail: null }, 2100);
    run = finishRun(run, 5200);
    expect(run.steps.map((s) => [s.stage, s.detail, s.startedAt, s.endedAt])).toEqual([
      ["detecting", null, 1000, 1200],
      ["retrieving", "40 passages", 1200, 2100],
      ["generating", null, 2100, 5200],
    ]);
    expect(seconds((run.finishedAt ?? 0) - run.startedAt)).toBe("4.2 s");
  });

  it("marks the step that was running when the answer failed", () => {
    const run = finishRun(
      addStatus(startRun(0, 1), { stage: "retrieving", detail: null }, 10),
      30,
      true,
    );
    expect(run.steps[0]).toMatchObject({ endedAt: 30, failed: true });
  });

  it("names the stages in the reader's terms", () => {
    expect(stepLabel("retrieving", 4)).toBe("Searching 4 jurisdictions");
    expect(stepLabel("retrieving", 1)).toBe("Searching 1 jurisdiction");
    expect(stepLabel("verifying", 4)).toBe("Checking citations");
  });
});
