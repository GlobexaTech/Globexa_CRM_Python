"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSession } from "@/auth/SessionProvider";
import { operations } from "@/services/operations";

export default function OAuthCallbackPage() {
  const { session } = useSession();
  const started = useRef(false);
  const [message, setMessage] = useState("Validating authorization callback…");
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!session?.tenant_id || started.current) return;
    started.current = true;
    const query = new URLSearchParams(window.location.search);
    const state = query.get("state");
    const code = query.get("code");
    const cancelled = query.has("error");
    // Remove transient authorization values from the address bar before any request.
    window.history.replaceState(null, "", "/integrations/callback");
    const correlation = sessionStorage.getItem("globexa-oauth-correlation");
    sessionStorage.removeItem("globexa-oauth-correlation");
    async function finish() {
      try {
        if (cancelled)
          throw new Error(
            "Provider authorization was cancelled or denied. Reconnect from Integrations when ready.",
          );
        if (!state || !code || !correlation)
          throw new Error(
            "Authorization context is missing. Start a new connection from Integrations.",
          );
        const pending: {
          integrationId?: string;
          tenantId?: string;
          startedAt?: number;
        } = JSON.parse(correlation);
        if (
          pending.tenantId !== session!.tenant_id ||
          !pending.integrationId ||
          !pending.startedAt ||
          Date.now() - pending.startedAt > 600000
        )
          throw new Error(
            "Authorization expired or belongs to a different workspace. Start again in the original workspace.",
          );
        const result = await operations.callback(pending.integrationId, {
          state,
          code,
        });
        setMessage(
          result.status === "connected"
            ? "The backend confirmed the integration is connected."
            : `Backend integration status: ${result.status}`,
        );
      } catch (error) {
        setFailed(true);
        setMessage(
          error instanceof Error
            ? error.message
            : "Authorization could not be completed. Start a new connection; do not retry an exchanged code.",
        );
      }
    }
    void finish();
  }, [session]);
  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <section className="card w-full max-w-xl space-y-4 p-6">
        <h1 className="text-2xl font-semibold">Integration authorization</h1>
        <p
          role={failed ? "alert" : "status"}
          className={failed ? "crm-error" : ""}
        >
          {message}
        </p>
        <p className="crm-muted">
          The provider code is exchanged by the backend. Client secrets and
          provider tokens stay on the server.
        </p>
        <Link className="crm-button" href="/integrations">
          Return to Integrations
        </Link>
      </section>
    </main>
  );
}
