"use client";

import { usageView, useUsage, type Usage } from "@/lib/usage";

/** UsageMeter spec: how much of the demo's daily allowance is left, so a limit never arrives as
 * a surprise. A label and the count, a 6px track on `bg-active` with an `accent` fill that turns
 * `warning` from 80% used, and the reset time, which says how many are left once it is low.
 * It is a `meter` with its value and maximum. */
export function UsageMeterView({ usage, now }: { usage: Usage; now: Date }) {
  const view = usageView(usage, now);
  return (
    <div className="flex w-full flex-col gap-1.5 text-small text-fg-muted">
      <div className="flex justify-between gap-2">
        <span>Demo questions</span>
        <strong className="font-semibold tabular-nums text-fg">{view.count}</strong>
      </div>
      <div
        role="meter"
        aria-label="Demo questions used"
        aria-valuenow={view.used}
        aria-valuemin={0}
        aria-valuemax={view.limit}
        className="h-1.5 overflow-hidden rounded-full bg-bg-active"
      >
        <div
          style={{ width: `${view.share * 100}%` }}
          className={`h-full rounded-[inherit] ${view.low ? "bg-warning" : "bg-accent"}`}
        />
      </div>
      <span className={view.low ? "text-warning" : undefined}>{view.note}</span>
    </div>
  );
}

/** The meter for this visitor's day. Without an API to ask (the static tier, a server that is
 * down) there is nothing to show, so it shows nothing. */
export function UsageMeter({ className }: { className?: string }) {
  const { data, dataUpdatedAt } = useUsage();
  if (!data) return null;
  return (
    <div className={className}>
      <UsageMeterView usage={data} now={new Date(dataUpdatedAt)} />
    </div>
  );
}
