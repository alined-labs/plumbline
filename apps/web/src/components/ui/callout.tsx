import type { ComponentType, ReactNode } from "react";

import {
  CircleCheckIcon,
  CircleDashedIcon,
  InfoIcon,
  OctagonAlertIcon,
  TriangleAlertIcon,
  type IconProps,
} from "@/components/icons";

// Callout spec: one short message in the tone of what it reports, with the tone's icon and a
// title. No coloured left border and no full-saturation fill.
const tones = {
  info: { box: "border-accent-border bg-accent-subtle", ink: "text-accent-text", Icon: InfoIcon },
  success: {
    box: "border-success-border bg-success-bg",
    ink: "text-success",
    Icon: CircleCheckIcon,
  },
  warning: {
    box: "border-warning-border bg-warning-bg",
    ink: "text-warning",
    Icon: TriangleAlertIcon,
  },
  danger: { box: "border-danger-border bg-danger-bg", ink: "text-danger", Icon: OctagonAlertIcon },
  neutral: {
    box: "border-neutral-border bg-neutral-bg",
    ink: "text-neutral",
    Icon: CircleDashedIcon,
  },
} satisfies Record<string, { box: string; ink: string; Icon: ComponentType<IconProps> }>;

export function Callout({
  tone,
  title,
  children,
  action,
}: {
  tone: keyof typeof tones;
  title: string;
  children?: ReactNode;
  /** One ghost or secondary small button, at the end. */
  action?: ReactNode;
}) {
  const { box, ink, Icon } = tones[tone];
  return (
    <div
      role={tone === "danger" || tone === "warning" ? "alert" : "status"}
      className={`grid grid-cols-[--spacing(5)_minmax(0,1fr)_auto] items-start gap-x-2.5 rounded-lg border px-3.5 py-3 text-ui text-fg ${box}`}
    >
      <span className={`flex h-5 items-center ${ink}`}>
        <Icon />
      </span>
      <p>
        <span className={`font-semibold ${ink}`}>{title}</span> {children}
      </p>
      {action}
    </div>
  );
}
