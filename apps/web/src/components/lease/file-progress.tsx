import { Spinner } from "@/components/answer/status-steps";
import { CircleCheckIcon, CircleXIcon, FileTextIcon } from "@/components/icons";
import type { StartedJob } from "@/lib/lease-job";
import { progress, steps, type StepState } from "@/lib/lease-steps";
import { formatBytes } from "@/lib/lease-file";

// Colour, icon and word together (DESIGN.md): the colour is never the only signal.
const STATE_STYLE: Record<StepState, string> = {
  done: "text-success",
  active: "font-medium text-fg",
  pending: "text-fg-subtle",
  failed: "text-danger",
};

/** Dropzone spec, the file row: the file's icon, name and size, then the four steps (finished
 * ones in `success` with a check, the one under way in `fg` with a spinner, the rest in
 * `fg-subtle`) and a thin bar. The bar has a value only once the checker counts clauses;
 * before that it says the work is under way without promising a time. */
export function FileProgress({ job }: { job: StartedJob }) {
  const value = progress(job);
  return (
    <div className="grid grid-cols-[--spacing(8)_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 rounded-lg border border-border bg-surface px-3.5 py-3">
      <span className="flex size-8 items-center justify-center rounded-md bg-surface-sunken text-fg-muted">
        <FileTextIcon />
      </span>
      <span className="truncate text-ui-strong">{job.file.name}</span>
      <span className="text-small tabular-nums text-fg-muted">{formatBytes(job.file.size)}</span>
      <ol
        aria-label="Steps of the check"
        className="col-start-2 col-end-[-1] flex flex-wrap gap-x-3.5 gap-y-1 text-small"
      >
        {steps(job).map((step) => (
          <li
            key={step.key}
            aria-current={step.state === "active" ? "step" : undefined}
            className={`inline-flex items-center gap-1 ${STATE_STYLE[step.state]}`}
          >
            {step.state === "done" && <CircleCheckIcon />}
            {step.state === "active" && <Spinner />}
            {step.state === "failed" && <CircleXIcon />}
            <span>
              {step.label}
              {step.detail && <span className="font-normal text-fg-subtle"> · {step.detail}</span>}
              {step.state === "pending" && <span className="sr-only"> (waiting)</span>}
              {step.state === "failed" && <span className="sr-only"> (failed)</span>}
            </span>
          </li>
        ))}
      </ol>
      {job.status !== "failed" && (
        <div
          role="progressbar"
          aria-label="Checking the lease"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={value === null ? undefined : Math.round(value * 100)}
          className="col-start-2 col-end-[-1] h-1 overflow-hidden rounded-full bg-bg-active"
        >
          <span
            className={`block h-full rounded-full bg-accent transition-[width] duration-(--pl-duration-base) ${
              value === null ? "w-2/5 animate-pulse motion-reduce:animate-none" : ""
            }`}
            style={value === null ? undefined : { width: `${value * 100}%` }}
          />
        </div>
      )}
    </div>
  );
}
