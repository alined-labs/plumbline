import { render, screen } from "@testing-library/react";

import { LeaseFailure } from "@/lib/lease-check";
import { IDLE, reduceJob, type JobAction, type StartedJob } from "@/lib/lease-job";

import { FileProgress } from "./file-progress";

function job(...actions: JobAction[]): StartedJob {
  const started = [
    { type: "start", file: { name: "lease.pdf", size: 1_468_006 } } as const,
    ...actions,
  ].reduce(reduceJob, IDLE);
  if (started.status === "idle") throw new Error("the check did not start");
  return started;
}

describe("FileProgress", () => {
  it("names the file and its size, and has the upload under way before the checker reports", () => {
    render(<FileProgress job={job()} />);
    expect(screen.getByText("lease.pdf")).toBeInTheDocument();
    expect(screen.getByText("1.4 MB")).toBeInTheDocument();
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Uploading");
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
    expect(screen.getByRole("progressbar", { name: "Checking the lease" })).not.toHaveAttribute(
      "aria-valuenow",
    );
  });

  it("shows finished steps, the clause count on the one under way, and a value on the bar", () => {
    render(
      <FileProgress
        job={job({
          type: "event",
          event: { type: "stage", stage: "checking", done: 7, total: 14 },
        })}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Uploaded",
      "Redacted",
      "Read",
      "Checking clauses · 7 of 14",
    ]);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
  });

  it("says in words which steps are waiting and which one failed, and drops the bar", () => {
    const failure = new LeaseFailure("timed_out", "The check took too long.");
    render(
      <FileProgress
        job={job(
          { type: "event", event: { type: "stage", stage: "redacting" } },
          { type: "fail", failure },
        )}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items[1]).toHaveTextContent("Redacting (failed)");
    expect(items[2]).toHaveTextContent("Reading (waiting)");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});
