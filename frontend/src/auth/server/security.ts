import { createCipheriv, createDecipheriv, randomBytes, createHash } from "node:crypto";

export class SessionError extends Error {
  constructor(public status: number, public code: string, message: string, public retryAfter?: string) {
    super(message);
  }
}

export function configuration() {
  const origin = process.env.APP_ORIGIN;
  const backend = process.env.BACKEND_API_URL;
  const redis = process.env.FRONTEND_REDIS_URL;
  const key = process.env.SESSION_ENCRYPTION_KEY;
  if (!origin || !backend || !redis || !key || !/^[a-f\d]{64}$/i.test(key)) {
    throw new SessionError(503, "session_configuration", "The session service is not configured.");
  }
  const app = new URL(origin);
  const api = new URL(backend);
  const testing = process.env.FRONTEND_ENV === "testing";
  if (app.origin !== origin || api.origin !== backend || app.username || api.username || app.password || api.password ||
      !["https:", "http:"].includes(api.protocol) || !["https:", "http:"].includes(app.protocol) ||
      (!testing && app.protocol !== "https:")) {
    throw new SessionError(503, "session_configuration", "The session service has invalid origins.");
  }
  return { origin, backend, redis, key: Buffer.from(key, "hex"), secure: !testing };
}

export function cookieName(secure: boolean) {
  return secure ? "__Host-globexa-session" : "globexa-test-session";
}

export function seal(value: unknown, key: Buffer): string {
  const nonce = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, nonce);
  cipher.setAAD(Buffer.from("globexa-frontend-session-v1"));
  const encrypted = Buffer.concat([cipher.update(JSON.stringify(value), "utf8"), cipher.final()]);
  return Buffer.concat([nonce, cipher.getAuthTag(), encrypted]).toString("base64url");
}

export function unseal<T>(ciphertext: string, key: Buffer): T {
  const value = Buffer.from(ciphertext, "base64url");
  if (value.length < 29) throw new Error("Invalid encrypted session");
  const cipher = createDecipheriv("aes-256-gcm", key, value.subarray(0, 12));
  cipher.setAAD(Buffer.from("globexa-frontend-session-v1"));
  cipher.setAuthTag(value.subarray(12, 28));
  return JSON.parse(Buffer.concat([cipher.update(value.subarray(28)), cipher.final()]).toString("utf8")) as T;
}

export function sessionKey(id: string) {
  if (!/^[a-f\d]{64}$/.test(id)) throw new SessionError(401, "session_expired", "Please sign in again.");
  return `globexa:frontend:session:${createHash("sha256").update(id).digest("hex")}`;
}

export function requireOrigin(request: Request, origin: string) {
  if (request.headers.get("origin") !== origin || request.headers.get("sec-fetch-site") === "cross-site") {
    throw new SessionError(403, "invalid_origin", "This request did not originate from this application.");
  }
}

export function requireVersion(actual: string, expected: string | null) {
  if (!expected || actual !== expected) throw new SessionError(409, "workspace_changed", "Your workspace changed. Reload this view before continuing.");
}

const allowedRoots = new Set(["leads", "contacts", "companies", "deals", "tasks", "notes", "activities", "campaigns", "integrations", "operations", "foundation", "users", "tenants"]);

/** No arbitrary hosts, auth token endpoints, traversal, encoded separators or forwarded headers. */
export function allowedApiPath(segments: string[], search = "") {
  const ownProfile = segments.length === 2 && segments[0] === "auth" && segments[1] === "me";
  if (!segments.length || (!allowedRoots.has(segments[0]) && !ownProfile) ||
      segments.some((part) => !/^[a-zA-Z\d_-]+$/.test(part) || part.length > 100)) {
    throw new SessionError(404, "unsupported_route", "This API route is unavailable.");
  }
  const query = new URLSearchParams(search);
  for (const key of query.keys()) {
    if (["tenant_id", "access_token", "refresh_token", "authorization"].includes(key.toLowerCase())) {
      throw new SessionError(400, "invalid_query", "The requested query is not supported.");
    }
  }
  if (query.toString().length > 8000) throw new SessionError(400, "invalid_query", "The query is too long.");
  return `/api/v1/${segments.join("/")}${query.size ? `?${query}` : ""}`;
}

export function publicFailure(error: unknown): Response {
  const known = error instanceof SessionError;
  const status = known ? error.status : 503;
  return Response.json({ detail: known ? error.message : "The session service is temporarily unavailable.", code: known ? error.code : "service_unavailable" }, {
    status,
    headers: { "Cache-Control": "no-store", ...(known && error.retryAfter ? { "Retry-After": error.retryAfter } : {}) },
  });
}
