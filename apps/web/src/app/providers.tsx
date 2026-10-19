"use client";

import { Tooltip } from "@base-ui/react/tooltip";
import type { ReactNode } from "react";

/** The tooltips' shared 400 ms delay (Toast spec: Tooltip). */
export function Providers({ children }: { children: ReactNode }) {
  return <Tooltip.Provider delay={400}>{children}</Tooltip.Provider>;
}
