"use client";
import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/auth/SessionProvider";
import { notifyWorkspace } from "@/components/WorkspaceSync";

export function useAction() {
  const cache = useQueryClient();
  const { session } = useSession();
  const busy = useRef(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  async function run<T>(operation: () => Promise<T>): Promise<T | undefined> {
    if (busy.current) return;
    busy.current = true;
    setPending(true);
    setError(null);
    setSuccess(false);
    try {
      const result = await operation();
      setSuccess(true);
      return result;
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The request could not be completed.",
      );
    } finally {
      // A sequence can partially persist before a later operation fails. Always
      // reconcile this exact workspace generation; a switched workspace is untouched.
      await cache.invalidateQueries({
        queryKey: [session?.tenant_id, session?.version],
      });
      notifyWorkspace(session?.tenant_id);
      busy.current = false;
      setPending(false);
    }
  }
  return { run, pending, error, success };
}
