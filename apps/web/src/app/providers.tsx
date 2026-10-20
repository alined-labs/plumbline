"use client";

import { Tooltip } from "@base-ui/react/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { PanelProvider } from "@/components/answer/panel-context";
import { LeaseJobProvider } from "@/components/lease/lease-job";
import { LeaseToasts } from "@/components/lease/lease-toasts";
import { ToastProvider } from "@/components/ui/toast";

/** The JSON routes' cache (TanStack Query), the tooltips' shared 400 ms delay (Toast spec:
 * Tooltip), the toasts, the source panel's state and the lease check, which goes on while the
 * reader is on another page. The query client lives in state, so a re-render never drops its
 * cache. */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <Tooltip.Provider delay={400}>
        <ToastProvider>
          <PanelProvider>
            <LeaseJobProvider>
              <LeaseToasts />
              {children}
            </LeaseJobProvider>
          </PanelProvider>
        </ToastProvider>
      </Tooltip.Provider>
    </QueryClientProvider>
  );
}
