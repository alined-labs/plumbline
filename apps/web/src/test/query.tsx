import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

/** A query client of its own for each test, so nothing one test cached reaches the next, and a
 * request that fails fails at once instead of being retried. Pass as `wrapper` to `render`. */
export function QueryWrapper({ children }: { children: ReactNode }) {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false } } }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
