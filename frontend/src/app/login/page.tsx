"use client";
import { useState, type FormEvent } from "react";
import { useSession } from "@/auth/SessionProvider";
import { ApiError } from "@/api/client";

export default function LoginPage() {
  const { login, logout, error: sessionError, loading } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryUntil, setRetryUntil] = useState(0);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    if (Date.now() < retryUntil) { setError("Please wait before trying to sign in again."); return; }
    setPending(true); setError(null);
    try { await login(email.trim(), password); setPassword(""); }
    catch (failure) {
      setError(failure instanceof Error ? failure.message : "Unable to sign in.");
      if (failure instanceof ApiError && failure.retryAfter) setRetryUntil(Date.now() + failure.retryAfter * 1000);
    } finally { setPending(false); }
  }
  return <main className="login-shell">
    <section className="login-card" aria-labelledby="login-title">
      <div className="login-brand">GLOBEXA<span>CRM</span></div>
      <h1 id="login-title">Welcome back</h1>
      <p>Sign in to your Globexa workspace.</p>
      <form onSubmit={submit} aria-busy={pending}>
        <label htmlFor="login-email">Email address</label>
        <input id="login-email" type="email" autoComplete="username" required maxLength={320} value={email} onChange={(event) => setEmail(event.target.value)} disabled={pending} />
        <label htmlFor="login-password">Password</label>
        <input id="login-password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} disabled={pending} />
        {(error || sessionError) && <p className="form-error" role="alert">{error || sessionError}</p>}
        <button type="submit" className="primary-btn" disabled={pending || loading}>{pending ? "Signing in…" : loading ? "Checking session…" : "Sign in"}</button>
      </form>
      {sessionError?.includes("sign-out") && <button type="button" onClick={() => { void logout().catch(() => {}); }}>Retry sign out</button>}
    </section>
  </main>;
}
