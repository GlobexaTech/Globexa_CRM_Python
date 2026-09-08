"use client";
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/auth/SessionProvider";
/** Cross-tab messages carry only an invalidation hint, never CRM records or credentials. */
export function notifyWorkspace(tenantId?: string) {
  if (tenantId && typeof BroadcastChannel !== "undefined") {
    const channel = new BroadcastChannel("globexa-workspace-updates");
    channel.postMessage({ tenantId });
    channel.close();
  }
}
export function WorkspaceSync() {
  const { session } = useSession();
  const cache = useQueryClient();
  useEffect(() => {
    if (!session) return;
    const tenant = session.tenant_id,
      version = session.version;
    const refresh = () => {
      void cache.invalidateQueries({ queryKey: [tenant, version] });
    };
    const channel =
      typeof BroadcastChannel === "undefined"
        ? null
        : new BroadcastChannel("globexa-workspace-updates");
    if (channel)
      channel.onmessage = (event: MessageEvent<unknown>) => {
        if (
          event.data &&
          typeof event.data === "object" &&
          "tenantId" in event.data &&
          event.data.tenantId === tenant
        )
          refresh();
      };
    window.addEventListener("focus", refresh);
    return () => {
      channel?.close();
      window.removeEventListener("focus", refresh);
    };
  }, [session, cache]);
  return null;
}
