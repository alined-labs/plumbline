import { Tooltip } from "@base-ui/react/tooltip";
import type { ReactElement } from "react";

/** Toast spec, Tooltip: the name of an icon-only control on the inverse ground, after the
 * provider's 400 ms on hover and at once on focus. It never holds anything to act on. */
export function Tip({
  label,
  side = "top",
  enabled = true,
  children,
}: {
  label: string;
  side?: "top" | "right" | "bottom" | "left";
  /** Off where the name is already visible. */
  enabled?: boolean;
  children: ReactElement;
}) {
  if (!enabled) return children;
  return (
    <Tooltip.Root>
      <Tooltip.Trigger render={children} />
      <Tooltip.Portal>
        <Tooltip.Positioner side={side} sideOffset={8} className="z-(--pl-z-tooltip)">
          <Tooltip.Popup className="rounded-sm bg-inverse px-2 py-1 text-small text-fg-inverse shadow-2">
            {label}
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
