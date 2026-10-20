import { done, failure, found, stage, started } from "@/test/job";

import { IDLE, type StartedJob } from "./lease-job";
import { announcement, progress, steps } from "./lease-steps";

describe("steps", () => {
  const states = (job: StartedJob) => steps(job).map((step) => step.state);

  it("shows the upload as the step under way until the checker reports a stage", () => {
    expect(states(started())).toEqual(["active", "pending", "pending", "pending"]);
    expect(steps(started())[0]?.label).toBe("Uploading");
  });

  it("moves down the list as the stages arrive", () => {
    expect(states(started(stage("uploaded")))).toEqual(["done", "active", "pending", "pending"]);
    expect(states(started(stage("redacting")))).toEqual(["done", "active", "pending", "pending"]);
    expect(states(started(stage("reading")))).toEqual(["done", "done", "active", "pending"]);
    expect(states(started(stage("checking")))).toEqual(["done", "done", "done", "active"]);
  });

  it("counts the clauses on the step under way, and names the total when it is done", () => {
    const checking = steps(started(stage("checking", 8, 14)))[3];
    expect(checking).toMatchObject({ label: "Checking clauses", detail: "8 of 14" });
    const finished = steps(started(stage("checking", 14, 14), done));
    expect(states(started(stage("checking", 14, 14), done))).toEqual([
      "done",
      "done",
      "done",
      "done",
    ]);
    expect(finished[3]).toMatchObject({ label: "Checked 14 clauses", detail: undefined });
    expect(steps(started(stage("checking", 1, 1), done))[3]?.label).toBe("Checked 1 clause");
  });

  it("marks the step a failure stopped", () => {
    expect(states(started(stage("reading"), { type: "fail", failure }))).toEqual([
      "done",
      "done",
      "failed",
      "pending",
    ]);
  });
});

describe("progress", () => {
  it("is unknown until clauses are counted, then the share checked, and 1 when done", () => {
    expect(progress(started(stage("reading")))).toBeNull();
    expect(progress(started(stage("checking", 0, 0)))).toBeNull();
    expect(progress(started(stage("checking", 7, 14)))).toBe(0.5);
    expect(progress(started(stage("checking", 7, 14), done))).toBe(1);
  });
});

describe("announcement", () => {
  it("says nothing when idle or failed (a failure announces itself)", () => {
    expect(announcement(IDLE)).toBe("");
    expect(announcement(started({ type: "fail", failure }))).toBe("");
  });

  it("names the step under way, without the clause counts", () => {
    expect(announcement(started())).toBe("Uploading…");
    expect(announcement(started(stage("redacting")))).toBe("Redacting…");
    expect(announcement(started(stage("checking", 3, 14)))).toBe("Checking clauses…");
  });

  it("gives the result, computed from the findings", () => {
    expect(announcement(started(done))).toBe("Lease checked: no findings.");
    expect(announcement(started(found(1), found(2, "check"), found(3), done))).toBe(
      "Lease checked: 3 findings. 2 conflict with the law, 1 worth checking.",
    );
    expect(announcement(started(found(1), done))).toBe(
      "Lease checked: 1 finding. 1 conflicts with the law.",
    );
  });
});
