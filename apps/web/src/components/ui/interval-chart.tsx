import { useId } from "react";

import { formatInterval, formatScore } from "@/lib/evals";

// Chart spec: scores near 1 are dots with whiskers (95% intervals in fg) on a 0 to 1 axis, never
// bars on a cut axis; series labelled directly; gridlines chart-grid, the axis chart-axis; the
// gate's threshold a dashed fg-muted rule; a caption that states the takeaway, and the numbers
// in a table behind "Show data". Stroke widths, the dash and the dot follow the reference chart
// (design/reference/Chart.html). Positions are percentages, so the track stretches with the
// page without distorting its dots or its text.

export type IntervalPoint = {
  label: string;
  value: number;
  low: number | null;
  high: number | null;
  n: number;
};

const TICKS = [0, 0.25, 0.5, 0.75, 1];
/** Labelled ticks: fewer than the gridlines, so they never collide on a phone (never rotated). */
const LABELLED = [0, 0.5, 1];

const percent = (value: number) => `${Math.min(1, Math.max(0, value)) * 100}%`;

export function IntervalChart({
  title,
  caption,
  points,
  threshold,
}: {
  title: string;
  /** The takeaway, in a sentence. */
  caption: string;
  points: IntervalPoint[];
  /** The gate's threshold for this metric, drawn as a dashed rule. */
  threshold?: number | undefined;
}) {
  const captionId = useId();
  return (
    <figure aria-labelledby={captionId} className="flex flex-col gap-3">
      <figcaption id={captionId} className="flex flex-col gap-1">
        <span className="text-ui-strong text-fg">{title}</span>
        <span className="text-small text-fg-muted">{caption}</span>
      </figcaption>
      <div aria-hidden="true" className="flex flex-col gap-1">
        {points.map((point) => (
          <div
            key={point.label}
            className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3"
          >
            <span className="w-16 truncate text-micro text-fg-muted">{point.label}</span>
            <svg className="h-7 w-full overflow-visible">
              {TICKS.map((tick) => (
                <line
                  key={tick}
                  x1={percent(tick)}
                  x2={percent(tick)}
                  y1="0"
                  y2="100%"
                  // The zero line is the axis (3:1); the others are gridlines.
                  className={tick === 0 ? "stroke-chart-axis" : "stroke-chart-grid"}
                  strokeWidth={1}
                />
              ))}
              {threshold !== undefined && (
                <line
                  x1={percent(threshold)}
                  x2={percent(threshold)}
                  y1="0"
                  y2="100%"
                  className="stroke-fg-muted"
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                />
              )}
              {point.low !== null && point.high !== null && (
                <>
                  <line
                    x1={percent(point.low)}
                    x2={percent(point.high)}
                    y1="50%"
                    y2="50%"
                    className="stroke-fg"
                    strokeWidth={1.5}
                  />
                  {[point.low, point.high].map((end) => (
                    <line
                      key={end}
                      x1={percent(end)}
                      x2={percent(end)}
                      y1="30%"
                      y2="70%"
                      className="stroke-fg"
                      strokeWidth={1.5}
                    />
                  ))}
                </>
              )}
              <circle cx={percent(point.value)} cy="50%" r={7} className="fill-chart-1" />
            </svg>
            <span className="w-9 text-right text-micro text-fg tabular-nums">
              {formatScore(point.value)}
            </span>
          </div>
        ))}
        <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-3">
          <span className="w-16" />
          <div className="relative h-4 text-micro text-fg-subtle tabular-nums">
            {LABELLED.map((tick) => (
              <span
                key={tick}
                className="absolute -translate-x-1/2 first:translate-x-0 last:-translate-x-full"
                style={{ left: percent(tick) }}
              >
                {String(tick)}
              </span>
            ))}
          </div>
          <span className="w-9" />
        </div>
      </div>
      <details className="text-small">
        <summary className="cursor-pointer text-accent underline underline-offset-2 hover:text-accent-hover">
          Show data
        </summary>
        <table className="mt-2 w-full border-separate border-spacing-0 text-ui tabular-nums">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr>
              <th scope="col" className="px-2 py-1 text-left text-micro font-medium text-fg-muted">
                Configuration
              </th>
              <th scope="col" className="px-2 py-1 text-right text-micro font-medium text-fg-muted">
                Score
              </th>
              <th scope="col" className="px-2 py-1 text-right text-micro font-medium text-fg-muted">
                95% interval
              </th>
              <th scope="col" className="px-2 py-1 text-right text-micro font-medium text-fg-muted">
                Questions
              </th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.label}>
                <th scope="row" className="px-2 py-1 text-left font-semibold">
                  {point.label}
                </th>
                <td className="px-2 py-1 text-right">{formatScore(point.value)}</td>
                <td className="px-2 py-1 text-right">
                  {formatInterval(point.low, point.high) ?? "–"}
                </td>
                <td className="px-2 py-1 text-right">{point.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
