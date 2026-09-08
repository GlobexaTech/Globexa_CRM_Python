import "server-only";
import { randomUUID } from "node:crypto";
import { cookies } from "next/headers";
import type { Session, Workspace } from "../types";
import { allowedApiPath, configuration, cookieName, publicFailure, requireOrigin, requireVersion, SessionError } from "./security";
import { deleteSession, loadSession, newSessionId, saveSession, type StoredSession, withSessionLock } from "./store";

const SESSION_SECONDS = 8 * 60 * 60;
const MAX_BODY_BYTES = 1024 * 1024;
type Tokens = { access_token: string; refresh_token: string; expires_in: number };

async function upstream(path: string, init: RequestInit = {}, session?: StoredSession) {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (session) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
    headers.set("X-Tenant-ID", session.public.tenant_id);
  }
  try {
    return await fetch(`${configuration().backend}${path}`, { ...init, headers, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(8000) });
  } catch {
    throw new SessionError(503, "backend_unavailable", "The CRM service is temporarily unavailable. The operation may need to be checked before retrying.");
  }
}

async function tokensFrom(response: Response): Promise<Tokens> {
  if (!response.ok) throw new SessionError(response.status === 429 ? 429 : 401, response.status === 429 ? "rate_limited" : "session_expired", response.status === 429 ? "Too many requests. Please wait before trying again." : "Please sign in again.", response.headers.get("retry-after") ?? undefined);
  const value = await response.json() as Tokens;
  if (!value.access_token || !value.refresh_token || !Number.isFinite(value.expires_in) || value.expires_in <= 0) {
    throw new SessionError(502, "invalid_session", "The CRM returned an invalid session.");
  }
  return value;
}

function initialSession(tokens: Tokens): StoredSession {
  // Claims only bootstrap the request context. Backend /me, /tenants and /permissions
  // validate the token and current membership before any browser session is issued.
  const claims = JSON.parse(Buffer.from(tokens.access_token.split(".")[1], "base64url").toString("utf8")) as { tenant_id?: string };
  if (!claims.tenant_id || !/^[a-f\d-]{36}$/i.test(claims.tenant_id)) throw new SessionError(502, "invalid_session", "The CRM returned an invalid session.");
  return {
    public: { user: { id: "", email: "", full_name: "", first_name: "", last_name: "" }, tenants: [], tenant_id: claims.tenant_id, role: "", permissions: [], version: randomUUID() },
    accessToken: tokens.access_token, refreshToken: tokens.refresh_token,
    expiresAt: Date.now() + tokens.expires_in * 1000, absoluteExpiry: Date.now() + SESSION_SECONDS * 1000,
  };
}

async function hydrate(session: StoredSession) {
  const responses = await Promise.all(["me", "tenants", "permissions"].map((resource) => upstream(`/api/v1/auth/${resource}`, {}, session)));
  if (responses.some((response) => !response.ok)) {
    const failed = responses.find((response) => !response.ok)!;
    throw new SessionError(failed.status === 401 || failed.status === 403 ? 401 : 503, "session_unavailable", "Your session could not be validated. Please sign in again.");
  }
  const [user, tenants, permissions] = await Promise.all(responses.map((response) => response.json())) as [{ id: string; email: string; full_name: string }, Workspace[], { permissions: string[] }];
  const membership = tenants.find((tenant) => tenant.id === session.public.tenant_id);
  if (!membership || !Array.isArray(permissions.permissions) || !user.id || !user.email) throw new SessionError(401, "invalid_membership", "Your workspace membership is no longer available.");
  const names = user.full_name.trim().split(/\s+/);
  const changed = session.public.role && (session.public.role !== membership.role || JSON.stringify(session.public.permissions) !== JSON.stringify(permissions.permissions));
  session.public = { user: { id: user.id, email: user.email, full_name: user.full_name, first_name: names[0] || "", last_name: names.slice(1).join(" ") }, tenants, tenant_id: membership.id, role: membership.role, permissions: permissions.permissions, version: changed ? randomUUID() : session.public.version };
  return session;
}

async function refresh(id: string, session: StoredSession) {
  try {
    const tokens = await tokensFrom(await upstream("/api/v1/auth/refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: session.refreshToken }) }));
    session.accessToken = tokens.access_token;
    session.refreshToken = tokens.refresh_token;
    session.expiresAt = Date.now() + tokens.expires_in * 1000;
    await hydrate(session);
    await saveSession(id, session, true);
    return session;
  } catch (error) {
    await deleteSession(id);
    throw error;
  }
}

async function currentId() {
  const config = configuration();
  const id = (await cookies()).get(cookieName(config.secure))?.value;
  if (!id) throw new SessionError(401, "session_expired", "Please sign in again.");
  return id;
}

async function setCookie(id: string, maxAge = SESSION_SECONDS) {
  const config = configuration();
  (await cookies()).set(cookieName(config.secure), id, { httpOnly: true, secure: config.secure, sameSite: "lax", path: "/", maxAge });
}

export async function readJson(request: Request): Promise<unknown> {
  if (!request.headers.get("content-type")?.startsWith("application/json")) throw new SessionError(415, "json_required", "Send an application/json request.");
  if (Number(request.headers.get("content-length") ?? 0) > MAX_BODY_BYTES) throw new SessionError(413, "body_too_large", "This request is too large.");
  const reader = request.body?.getReader();
  if (!reader) throw new SessionError(400, "invalid_json", "A JSON request body is required.");
  let size = 0;
  const chunks: Uint8Array[] = [];
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > MAX_BODY_BYTES) { await reader.cancel(); throw new SessionError(413, "body_too_large", "This request is too large."); }
    chunks.push(value);
  }
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8")); }
  catch { throw new SessionError(400, "invalid_json", "The request body is not valid JSON."); }
}

function responseSession(session: Session) { return Response.json(session, { headers: { "Cache-Control": "no-store" } }); }

export async function sessionLogin(request: Request) {
  try {
    requireOrigin(request, configuration().origin);
    const body = await readJson(request) as { email?: unknown; password?: unknown };
    if (!body || typeof body.email !== "string" || !body.email.includes("@") || body.email.length > 320 || typeof body.password !== "string" || body.password.length < 1 || body.password.length > 1024) {
      throw new SessionError(422, "invalid_credentials", "Enter your email address and password.");
    }
    const response = await upstream("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ username: body.email, password: body.password }) });
    if (response.status === 401) throw new SessionError(401, "invalid_credentials", "Email or password is incorrect.");
    const session = await hydrate(initialSession(await tokensFrom(response)));
    const id = newSessionId();
    const previous = (await cookies()).get(cookieName(configuration().secure))?.value;
    if (previous) await withSessionLock(previous, () => deleteSession(previous));
    await saveSession(id, session);
    await setCookie(id);
    return responseSession(session.public);
  } catch (error) { return publicFailure(error); }
}

export async function sessionGet() {
  try {
    const id = await currentId();
    return await withSessionLock(id, async () => {
      let session = await loadSession(id);
      if (session.expiresAt < Date.now() + 30000) session = await refresh(id, session);
      else {
        try { await hydrate(session); }
        catch (error) {
          if (!(error instanceof SessionError) || error.status !== 401) throw error;
          session = await refresh(id, session);
        }
        await saveSession(id, session, true);
      }
      return responseSession(session.public);
    });
  } catch (error) { return publicFailure(error); }
}

export async function sessionLogout(request: Request) {
  try {
    requireOrigin(request, configuration().origin);
    let id: string;
    try { id = await currentId(); }
    catch (error) { if (!(error instanceof SessionError) || error.status !== 401) throw error; await setCookie("", 0); return new Response(null, { status: 204 }); }
    await withSessionLock(id, async () => {
      let session: StoredSession | undefined;
      try { session = await loadSession(id); }
      catch (error) { if (!(error instanceof SessionError) || error.status !== 401) throw error; }
      // Delete first: a provider/backend outage must never keep this browser signed in.
      await deleteSession(id);
      if (session) { try { await upstream("/api/v1/auth/logout", { method: "POST" }, session); } catch {} }
    });
    await setCookie("", 0);
    return new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } });
  } catch (error) { return publicFailure(error); }
}

export async function sessionSwitch(request: Request) {
  try {
    requireOrigin(request, configuration().origin);
    const body = await readJson(request) as { tenant_id?: unknown } | null;
    const tenant_id = body?.tenant_id;
    if (typeof tenant_id !== "string" || !/^[a-f\d-]{36}$/i.test(tenant_id)) throw new SessionError(422, "invalid_workspace", "Choose an available workspace.");
    const id = await currentId();
    return await withSessionLock(id, async () => {
      let session = await loadSession(id);
      requireVersion(session.public.version, request.headers.get("x-workspace-version"));
      if (session.expiresAt < Date.now() + 30000) session = await refresh(id, session);
      await hydrate(session);
      if (!session.public.tenants.some((tenant) => tenant.id === tenant_id)) throw new SessionError(403, "invalid_membership", "You do not belong to this workspace.");
      const response = await upstream(`/api/v1/auth/switch-tenant/${tenant_id}`, { method: "POST" }, session);
      if (response.status === 403) throw new SessionError(403, "invalid_membership", "You do not belong to this workspace.");
      const next = await hydrate(initialSession(await tokensFrom(response)));
      if (next.public.tenant_id !== tenant_id || next.public.user.id !== session.public.user.id) throw new SessionError(502, "invalid_session", "The workspace change could not be verified.");
      next.absoluteExpiry = session.absoluteExpiry;
      await saveSession(id, next, true);
      return responseSession(next.public);
    });
  } catch (error) { return publicFailure(error); }
}

const forbiddenResponseKeys = new Set(["access_token", "refresh_token", "password", "credentials", "client_secret", "api_key", "encrypted_credentials", "encrypted_tokens"]);
function safeBody(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(safeBody);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).filter(([key]) => !forbiddenResponseKeys.has(key.toLowerCase()) && key !== "input").map(([key, val]) => [key, safeBody(val)]));
  return value;
}

export async function proxy(request: Request, segments: string[]) {
  try {
    const mutation = !["GET", "HEAD"].includes(request.method);
    if (mutation) requireOrigin(request, configuration().origin);
    const path = allowedApiPath(segments, new URL(request.url).search);
    const id = await currentId();
    const body = mutation && request.method !== "DELETE" ? await readJson(request) : undefined;
    const key = request.headers.get("idempotency-key");
    if (key && !/^[\x21-\x7E]{8,100}$/.test(key)) throw new SessionError(422, "invalid_idempotency_key", "The request identifier is invalid.");
    return await withSessionLock(id, async () => {
      let session = await loadSession(id);
      requireVersion(session.public.version, request.headers.get("x-workspace-version"));
      const refreshed = session.expiresAt < Date.now() + 30000;
      if (refreshed) session = await refresh(id, session);
      requireVersion(session.public.version, request.headers.get("x-workspace-version"));
      const init: RequestInit = { method: request.method, headers: { "Content-Type": "application/json", ...(key ? { "Idempotency-Key": key } : {}) }, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) };
      let response = await upstream(path, init, session);
      // An authenticated 401 means the action was rejected. Only this case receives
      // a single bounded replay after refreshing. Timeouts and 5xx never replay writes.
      if (response.status === 401) {
        if (refreshed) { await deleteSession(id); throw new SessionError(401, "session_expired", "Please sign in again."); }
        session = await refresh(id, session);
        requireVersion(session.public.version, request.headers.get("x-workspace-version"));
        response = await upstream(path, init, session);
        if (response.status === 401) await deleteSession(id);
      }
      requireVersion((await loadSession(id)).public.version, session.public.version);
      if (response.status >= 500) throw new SessionError(response.status, "backend_error", "The CRM could not complete this request.", response.headers.get("retry-after") ?? undefined);
      const headers: Record<string, string> = { "Cache-Control": "no-store", "X-Workspace-Version": session.public.version };
      const retryAfter = response.headers.get("retry-after");
      if (retryAfter) headers["Retry-After"] = retryAfter;
      if (response.status === 204 || request.method === "HEAD") return new Response(null, { status: response.status, headers });
      const result = await response.json();
      return Response.json(safeBody(result), { status: response.status, headers });
    });
  } catch (error) { return publicFailure(error); }
}
