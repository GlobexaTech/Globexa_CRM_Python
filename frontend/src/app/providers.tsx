"use client";
import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionProvider } from "@/auth/SessionProvider";
import { ToastProvider } from "@/components/ToastProvider";
import { ConfirmProvider } from "@/components/ConfirmProvider";
import { ApiError } from "@/api/client";
import { WorkspaceSync } from "@/components/WorkspaceSync";

export default function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: {
    queries: { staleTime: 15000, gcTime: 300000, networkMode: "always", refetchOnWindowFocus: false, retry: (attempt, error) => attempt < 1 && error instanceof ApiError && error.status >= 500 },
    mutations: { retry: false },
  } }));
  return <QueryClientProvider client={client}><SessionProvider><WorkspaceSync /><ToastProvider><ConfirmProvider>{children}</ConfirmProvider></ToastProvider></SessionProvider></QueryClientProvider>;
}
