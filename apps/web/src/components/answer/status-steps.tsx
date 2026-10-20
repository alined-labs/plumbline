import { CircleCheckIcon, CircleXIcon } from "@/components/icons";
import { seconds, stepLabel, type Run } from "@/lib/run";

/** The active-step spinner; under reduced motion it stops turning and stays a ring. */
export function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="inline-block size-3.5 animate-spin rounded-full border-2 border-accent-subtle-hover border-t-accent motion-reduce:animate-none"
    />
  );
}

/** StatusSteps spec: one row per stage the stream reported, so the wait reads as work being
 * checked. The visible list is quiet; one polite line announces the active step only. */
export function StatusSteps({ run }: { run: Run }) {
  const active = run.steps.find((step) => step.endedAt === null);
  return (
    <div>
      <ol aria-label="What Plumbline is doing" className="flex flex-col text-ui">
        {run.steps.map((step) => {
          const done = step.endedAt !== null && !step.failed;
          return (
            <li
              key={step.stage}
              className={`grid grid-cols-[--spacing(5)_minmax(0,1fr)_auto] items-start gap-x-2.5 py-1.25 ${
                step.failed ? "text-danger" : done ? "text-fg-muted" : "font-medium text-fg"
              }`}
            >
              <span className="flex size-5 items-center justify-center">
                {step.failed ? (
                  <CircleXIcon />
                ) : done ? (
                  <CircleCheckIcon className="text-success" />
                ) : (
                  <Spinner />
                )}
              </span>
              <span>
                {stepLabel(step.stage, run.scope)}
                {step.detail && (
                  <span className="font-normal text-fg-subtle"> · {step.detail}</span>
                )}
                {step.failed && <span className="sr-only"> (failed)</span>}
              </span>
              <span className="font-mono text-code-sm tabular-nums text-fg-subtle">
                {step.endedAt !== null && seconds(step.endedAt - step.startedAt)}
              </span>
            </li>
          );
        })}
      </ol>
      {run.finishedAt === null && (
        <p aria-live="polite" className="sr-only">
          {active ? `${stepLabel(active.stage, run.scope)}…` : ""}
        </p>
      )}
    </div>
  );
}
