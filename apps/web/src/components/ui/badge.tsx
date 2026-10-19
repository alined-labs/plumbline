import type { ComponentType, ReactNode } from "react";

import {
  CircleCheckIcon,
  CircleDashedIcon,
  InfoIcon,
  OctagonAlertIcon,
  TriangleAlertIcon,
  type IconProps,
} from "@/components/icons";

// Badge spec: a status always pairs its colour with its icon and a word.
const tones = {
  success: { className: "border-success-border bg-success-bg text-success", Icon: CircleCheckIcon },
  warning: {
    className: "border-warning-border bg-warning-bg text-warning",
    Icon: TriangleAlertIcon,
  },
  danger: { className: "border-danger-border bg-danger-bg text-danger", Icon: OctagonAlertIcon },
  neutral: {
    className: "border-neutral-border bg-neutral-bg text-neutral",
    Icon: CircleDashedIcon,
  },
  info: { className: "border-accent-border bg-accent-subtle text-accent-text", Icon: InfoIcon },
} satisfies Record<string, { className: string; Icon: ComponentType<IconProps> }>;

export type BadgeTone = keyof typeof tones;

export function Badge({ tone, children }: { tone: BadgeTone; children: ReactNode }) {
  const { className, Icon } = tones[tone];
  return (
    <span
      className={`inline-flex h-5.5 items-center gap-1 whitespace-nowrap rounded-sm border px-1.75 text-micro font-semibold ${className}`}
    >
      <Icon size={14} strokeWidth={2} />
      {children}
    </span>
  );
}

/** A jurisdiction's ISO 3166 code in mono, never a flag. */
export function CodeBadge({ code }: { code: string }) {
  return (
    <span className="inline-flex h-5 items-center whitespace-nowrap rounded-sm border border-border-strong bg-surface px-1.5 font-mono text-code-sm font-medium text-fg-muted">
      {code}
    </span>
  );
}
