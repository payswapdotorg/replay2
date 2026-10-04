"use client";

/**
 * Engineering Lab — TanStack Query provider (B3-a).
 *
 * Scoped to the Lab console ONLY: the replay and mission-control views keep
 * their existing fetch/poll pattern, and layout.tsx is untouched. Defaults are
 * conservative: 15s staleness, no refetch-on-focus, a single retry — the lab
 * APIs are deterministic fixture-grade endpoints, never a live firehose.
 */

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

export function QueryProvider({ children }: { children: ReactNode }) {
  // Created once per mount via lazy initializer; avoids re-render churn.
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
