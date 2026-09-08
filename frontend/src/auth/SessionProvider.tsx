"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, cancelRequests, configureSession, decodeResponse } from "@/api/client";
import type { Session } from "./types";

interface SessionContext {
  session: Session | null;
  loading: boolean;
  error: string | null;
  can(permission: string): boolean;
  login(email: string, password: string): Promise<void>;
  logout(): Promise<void>;
  switchTenant(id: string): Promise<void>;
  refreshSession(): Promise<void>;
}
const Context = createContext<SessionContext | undefined>(undefined);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const current = useRef<Session | null>(null);
  const epoch = useRef(0);
  const queryClient = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const channel = useRef<BroadcastChannel | null>(null);

  const clear = useCallback(() => {
    epoch.current += 1;
    cancelRequests();
    configureSession(null);
    current.current = null;
    setSession(null);
    void queryClient.cancelQueries();
    queryClient.clear();
    return epoch.current;
  }, [queryClient]);

  const adopt = useCallback((value: Session) => {
    if (current.current?.version !== value.version) {
      cancelRequests();
      void queryClient.cancelQueries();
      queryClient.clear();
    }
    configureSession(value.version);
    current.current = value;
    setSession(value);
    setError(null);
  }, [queryClient]);

  const refreshSession = useCallback(async () => {
    const requestEpoch = epoch.current;
    try {
      const value = await decodeResponse<Session>(await fetch("/api/session", { cache: "no-store", credentials: "same-origin" }));
      if (requestEpoch === epoch.current) adopt(value);
    } catch (failure) {
      if (requestEpoch !== epoch.current) return;
      clear();
      setError(failure instanceof ApiError && failure.status === 401 ? null : failure instanceof Error ? failure.message : "Unable to restore your session.");
    } finally { if (requestEpoch === epoch.current || current.current === null) setLoading(false); }
  }, [adopt, clear]);

  useEffect(() => {
    configureSession(null, (status) => {
      clear();
      if (status === 401) { setError("Your session expired. Please sign in again."); setLoading(false); }
      else { setLoading(true); void refreshSession(); }
    });
    const restoration = window.setTimeout(() => { void refreshSession(); }, 0);
    const broadcast = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("globexa-session-change") : null;
    channel.current = broadcast;
    if (broadcast) broadcast.onmessage = () => { clear(); setLoading(true); void refreshSession(); };
    // Membership/permission changes and a workspace switch in another tab are
    // revalidated on focus before displaying that workspace again.
    const focus = () => { void refreshSession(); };
    window.addEventListener("focus", focus);
    return () => { window.clearTimeout(restoration); broadcast?.close(); channel.current = null; window.removeEventListener("focus", focus); };
  }, [clear, refreshSession]);

  useEffect(() => {
    if (!loading && !session && pathname !== "/login") router.replace("/login");
    if (!loading && session && pathname === "/login") router.replace("/");
  }, [loading, session, pathname, router]);

  const login = useCallback(async (email: string, password: string) => {
    const requestEpoch = clear();
    const value = await decodeResponse<Session>(await fetch("/api/session", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) }));
    if (epoch.current === requestEpoch) { epoch.current += 1; adopt(value); setLoading(false); channel.current?.postMessage("changed"); router.replace("/"); }
  }, [adopt, clear, router]);

  const logout = useCallback(async () => {
    clear();
    setLoading(true);
    try {
      await decodeResponse<void>(await fetch("/api/session", { method: "DELETE", credentials: "same-origin" }));
      channel.current?.postMessage("changed");
      setError(null);
    } catch (failure) {
      setError("Server sign-out could not be confirmed. Please retry sign-out before closing this browser.");
      throw failure;
    } finally { setLoading(false); router.replace("/login"); }
  }, [clear, router]);

  const switchTenant = useCallback(async (id: string) => {
    const previous = current.current;
    if (!previous?.tenants.some((tenant) => tenant.id === id)) throw new ApiError(403, "Choose an available workspace.");
    const requestEpoch = clear();
    setLoading(true);
    try {
      const value = await decodeResponse<Session>(await fetch("/api/session/tenant", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-Workspace-Version": previous.version }, body: JSON.stringify({ tenant_id: id }) }));
      if (epoch.current === requestEpoch) { epoch.current += 1; adopt(value); channel.current?.postMessage("changed"); router.replace("/"); }
    } catch (failure) {
      if (epoch.current === requestEpoch) await refreshSession();
      throw failure;
    } finally { setLoading(false); }
  }, [adopt, clear, refreshSession, router]);

  const value: SessionContext = { session, loading, error, can: (permission) => !!session?.permissions.includes(permission), login, logout, switchTenant, refreshSession };
  return <Context.Provider value={value}>
    {pathname === "/login" ? children : loading ? <main className="session-state" role="status"><h1>Opening your workspace…</h1><p>Checking your session and permissions.</p></main> : session ? <div key={`${session.tenant_id}:${session.version}`}>{children}</div> : <main className="session-state" role="status"><p>{error || "Redirecting to sign in…"}</p></main>}
  </Context.Provider>;
}

export function useSession() {
  const context = useContext(Context);
  if (!context) throw new Error("useSession requires SessionProvider");
  return context;
}
