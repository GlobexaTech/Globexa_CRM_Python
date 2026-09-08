"use client";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { useSession } from "@/auth/SessionProvider";

export function useResource<T>(path: string, enabled = true) {
  const { session } = useSession();
  return useQuery<T, ApiError>({
    queryKey: [session?.tenant_id, session?.version, path],
    queryFn: ({ signal }) => api.get<T>(path, { signal }),
    enabled: Boolean(session) && enabled,
    staleTime: 15_000,
    retry: false,
  });
}
