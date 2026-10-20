"use client";

import { Tooltip } from "@base-ui/react/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { ToastProvider } from "@/components/ui/toast";

/** The JSON routes' cache (TanStack Query), the tooltips' shared 400 ms delay (Toast spec:
 * Tooltip) and the toasts. The query client lives in state, so a re-render never drops its
 * cache. */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <Tooltip.Provider delay={400}>
        <ToastProvider>{children}</ToastProvider>
      </Tooltip.Provider>
    </QueryClientProvider>
  );
}
