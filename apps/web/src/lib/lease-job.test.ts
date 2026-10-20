import { done, failure, file, found, run, stage, start, started } from "@/test/job";

import { IDLE, reduceJob } from "./lease-job";

describe("reduceJob", () => {
  it("starts running, with nothing reported yet", () => {
    expect(run(start)).toEqual({
      status: "running",
      file,
      stage: null,
      clauses: null,
      findings: [],
    });
  });

  it("follows the stages and the clause counts, and keeps the counts between stages", () => {
    const job = started(stage("redacting"), stage("checking", 0, 14), stage("checking", 8, 14));
    expect(job).toMatchObject({ stage: "checking", clauses: { done: 8, total: 14 } });
    expect(reduceJob(job, stage("checking"))).toMatchObject({ clauses: { done: 8, total: 14 } });
  });

  it("adds findings in the order they arrive, once each", () => {
    const job = started(found(1), found(2, "check"), found(2, "check"));
    expect(job.status === "running" && job.findings.map((f) => f.n)).toEqual([1, 2]);
  });

  it("finishes with the findings and the lease's language", () => {
    const job = started(found(1), done);
    expect(job).toMatchObject({ status: "done", language: "en" });
    expect(job.findings).toHaveLength(1);
  });

  it("fails with what it had, and ignores what arrives after", () => {
    const job = started(stage("reading"), found(1), { type: "fail", failure });
    expect(job).toMatchObject({ status: "failed", stage: "reading", failure });
    expect(job.findings).toHaveLength(1);
    expect(reduceJob(job, found(2))).toBe(job);
    expect(reduceJob(job, done)).toBe(job);
  });

  it("ignores a failure with no check running, and goes back to idle on reset", () => {
    expect(run({ type: "fail", failure })).toBe(IDLE);
    expect(run(start, done, { type: "fail", failure }).status).toBe("done");
    expect(run(start, found(1), { type: "reset" })).toBe(IDLE);
  });

  it("starts a second check from nothing", () => {
    expect(run(start, found(1), done, start)).toMatchObject({ status: "running", findings: [] });
  });
});
