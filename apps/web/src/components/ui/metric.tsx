import type { ReactNode } from "react";

// Metric spec: one headline number with its uncertainty underneath, in a grid of columns at
// least 170px wide (five across on a desktop, two on a phone).

export function MetricGrid({ label, children }: { label: string; children: ReactNode }) {
  return (
    // The name sits on a wrapper: a role on the <dl> itself would hide its terms from it.
    <div role="group" aria-label={label}>
      <dl className="grid grid-cols-[repeat(auto-fit,minmax(--spacing(42.5),1fr))] gap-3">
        {children}
      </dl>
    </div>
  );
}

export function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  /** The interval, or what stands in for one ("p50 3.1 s"). */
  detail?: string | undefined;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-surface px-4 py-3.5">
      <dt className="text-small font-medium text-fg-muted">{label}</dt>
      <dd className="text-kpi text-fg tabular-nums">{value}</dd>
      {detail && <dd className="font-mono text-code-sm text-fg-subtle">{detail}</dd>}
    </div>
  );
}
