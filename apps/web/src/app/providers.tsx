"use client";

import { Tooltip } from "@base-ui/react/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

/** The JSON routes' cache (TanStack Query) and the tooltips' shared 400 ms delay (Toast spec:
 * Tooltip). The query client lives in state, so a re-render never drops its cache. */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <Tooltip.Provider delay={400}>{children}</Tooltip.Provider>
    </QueryClientProvider>
  );
}
