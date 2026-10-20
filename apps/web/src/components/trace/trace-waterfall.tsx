import { duration, type SpanKind, type TraceSpan } from "@/lib/trace";

// Bar colours by kind (TraceWaterfall spec): retrieval chart-3, model calls chart-1,
// verification chart-2, everything else chart-5. A replayed span is an outline only, and a
// failed span is hatched in danger with a danger outline, so it reads without colour.
const FILL: Record<SpanKind, string> = {
  retrieval: "bg-chart-3",
  model: "bg-chart-1",
  verification: "bg-chart-2",
  other: "bg-chart-5",
};
const OUTLINE: Record<SpanKind, string> = {
  retrieval: "border-2 border-chart-3",
  model: "border-2 border-chart-1",
  verification: "border-2 border-chart-2",
  other: "border-2 border-chart-5",
};
const FAILED =
  "border border-danger bg-[repeating-linear-gradient(45deg,var(--pl-color-danger)_0_3px,transparent_3px_6px)]";

// Three ticks fit a panel-width track; five wrapped their labels.
const TICKS = [0, 0.5, 1];

// The axis and the rows share one grid, so a bar sits under the tick it belongs to: a name
// column, the time track, and a fixed column for the duration.
const GRID = "grid grid-cols-[40%_minmax(0,1fr)_--spacing(16)] items-center gap-x-3";

function barClass(span: TraceSpan): string {
  if (span.failed) return FAILED;
  return span.cached ? `${OUTLINE[span.kind]} bg-transparent` : FILL[span.kind];
}

/** TraceWaterfall spec: how one answer was produced, each stage as a row with its duration bar
 * on a shared time axis. The bars are drawn for the eye; each row says its name and duration
 * in text, so nothing depends on seeing them. */
export function TraceWaterfall({
  spans,
  total,
  label,
}: {
  spans: TraceSpan[];
  /** The answer's total time in milliseconds: the axis runs from 0 to here. */
  total: number;
  label: string;
}) {
  // A stage that took no time still needs a mark, and an all-zero trace needs an axis.
  const axis = Math.max(total, 1);
  return (
    <div className="flex flex-col gap-1.5">
      <div aria-hidden="true" className={`${GRID} font-mono text-code-sm text-fg-subtle`}>
        <span className="col-start-2 flex justify-between">
          {TICKS.map((tick) => (
            <span key={tick} className="whitespace-nowrap">
              {duration(axis * tick)}
            </span>
          ))}
        </span>
      </div>
      <ol aria-label={label} className="flex flex-col text-ui">
        {spans.map((span) => (
          <li key={span.name} className={`${GRID} border-t border-border-subtle py-1.5`}>
            <span className="truncate">{span.name}</span>
            <span aria-hidden="true" className="relative h-2.5">
              <span
                className={`absolute inset-y-0 min-w-0.5 rounded-xs ${barClass(span)}`}
                style={{
                  left: `${(span.start / axis) * 100}%`,
                  width: `${(span.duration / axis) * 100}%`,
                }}
              />
            </span>
            <span className="text-right font-mono text-code-sm tabular-nums text-fg-muted">
              {duration(span.duration)}
              {span.failed && <span className="sr-only"> (failed)</span>}
              {span.cached && <span className="sr-only"> (replayed)</span>}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
