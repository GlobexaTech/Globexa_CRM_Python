import { test } from "node:test";
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { allowedApiPath, configuration, cookieName, publicFailure, requireOrigin, requireVersion, seal, sessionKey, SessionError, unseal } from "../../src/auth/server/security";
import { api, ApiError, configureSession, decodeResponse } from "../../src/api/client";

test("AES-GCM sessions conceal credentials and use a fresh nonce", () => {
  const key = randomBytes(32);
  const source = { accessToken: randomBytes(40).toString("hex"), refreshToken: randomBytes(40).toString("hex"), tenant: "A" };
  const a = seal(source, key);
  const b = seal(source, key);
  assert.notEqual(a, b);
  assert.equal(a.includes(source.accessToken), false);
  assert.deepEqual(unseal(a, key), source);
});

test("altered ciphertext and wrong key cannot restore sessions", () => {
  const key = randomBytes(32);
  const encrypted = seal({ permission: "leads:read" }, key);
  const tampered = Buffer.from(encrypted, "base64url");
  tampered[30] ^= 1;
  assert.throws(() => unseal(tampered.toString("base64url"), key));
  assert.throws(() => unseal(encrypted, randomBytes(32)));
});

test("session storage keys hash validated opaque identifiers", () => {
  const id = randomBytes(32).toString("hex");
  assert.ok(!sessionKey(id).includes(id));
  for (const value of ["", "../admin", "jwt.token.signature", id + "\n"]) assert.throws(() => sessionKey(value));
});

test("write protection rejects missing, foreign and cross-site Origins", () => {
  const origin = "https://crm.example.test";
  assert.doesNotThrow(() => requireOrigin(new Request(`${origin}/api/session`, { method: "POST", headers: { Origin: origin } }), origin));
  const cases: Record<string, string>[] = [{}, { Origin: "https://attacker.example.test" }, { Origin: origin, "Sec-Fetch-Site": "cross-site" }];
  for (const headers of cases) {
    assert.throws(() => requireOrigin(new Request(`${origin}/api/session`, { method: "POST", headers }), origin), (error) => error instanceof SessionError && error.status === 403);
  }
});

test("workspace versions reject stale and missing versions", () => {
  requireVersion("A-v2", "A-v2");
  for (const version of [null, "A-v1", "B-v2", ""]) assert.throws(() => requireVersion("A-v2", version), (error) => error instanceof SessionError && error.code === "workspace_changed");
});

test("proxy allows CRM paths and preserves legitimate bounded query filters", () => {
  assert.equal(allowedApiPath(["operations", "customers", "contacts", "contact-id"], "?limit=25&offset=0"), "/api/v1/operations/customers/contacts/contact-id?limit=25&offset=0");
  assert.equal(allowedApiPath(["leads"], "?search=A%20B"), "/api/v1/leads?search=A+B");
});

test("proxy rejects auth endpoints, traversal, injected hosts and tenant queries", () => {
  for (const path of [[], ["auth", "refresh"], ["auth", "login"], ["leads", ".."], ["leads", "%2Fauth"], ["https:", "example.test"], ["leads", "a/b"], ["leads", "a\\b"]]) assert.throws(() => allowedApiPath(path));
  for (const query of ["?tenant_id=another", "?access_token=secret", "?refresh_token=secret", `?search=${"a".repeat(8001)}`]) assert.throws(() => allowedApiPath(["leads"], query));
});

test("only the authenticated own-profile endpoint is exposed from the auth namespace", () => {
  assert.equal(allowedApiPath(["auth", "me"]), "/api/v1/auth/me");
  for (const path of [["auth"], ["auth", "login"], ["auth", "refresh"], ["auth", "logout"], ["auth", "tenants"], ["auth", "me", "refresh"]]) assert.throws(() => allowedApiPath(path));
});

test("public errors conceal unexpected stack and credential messages", async () => {
  const value = randomBytes(32).toString("hex");
  const response = publicFailure(new Error(`Redis failure ${value}`));
  assert.equal(response.status, 503);
  assert.equal((await response.text()).includes(value), false);
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("rate errors preserve Retry-After without exposing internals", async () => {
  const response = publicFailure(new SessionError(429, "rate_limited", "Please wait.", "60"));
  assert.equal(response.headers.get("retry-after"), "60");
  await assert.rejects(() => decodeResponse(response), (error) => error instanceof ApiError && error.status === 429 && error.retryAfter === 60);
});

test("validation errors map backend field locations into form errors", async () => {
  const response = Response.json({ detail: [{ loc: ["body", "email"], msg: "Enter a valid email" }] }, { status: 422 });
  await assert.rejects(() => decodeResponse(response), (error) => error instanceof ApiError && error.fields?.email === "Enter a valid email" && error.status === 422);
});

test("empty success responses remain empty", async () => {
  assert.equal(await decodeResponse(new Response(null, { status: 204 })), undefined);
});

test("workspace switch aborts the old request and rejects a late transport result", async () => {
  const original = globalThis.fetch;
  let resolveResponse!: (response: Response) => void;
  let aborted = false;
  globalThis.fetch = async (_input, init) => {
    init?.signal?.addEventListener("abort", () => { aborted = true; });
    return new Promise<Response>((resolve) => { resolveResponse = resolve; });
  };
  try {
    configureSession("tenant-A-v1");
    const pending = api.get("/leads");
    configureSession("tenant-B-v1");
    resolveResponse(Response.json({ items: [{ title: "Old workspace data" }] }, { headers: { "X-Workspace-Version": "tenant-A-v1" } }));
    await assert.rejects(() => pending, (error) => error instanceof ApiError && error.code === "workspace_changed");
    assert.equal(aborted, true);
  } finally { globalThis.fetch = original; configureSession(null); }
});

test("signed-out client refuses CRM requests before any network call", async () => {
  configureSession(null);
  await assert.rejects(() => api.get("/leads"), (error) => error instanceof ApiError && error.status === 401);
});

test("workspace switch during response body decoding rejects the old result", async () => {
  const original = globalThis.fetch;
  let finishBody!: (value: unknown) => void;
  let startedBody!: () => void;
  const bodyStarted = new Promise<void>((resolve) => { startedBody = resolve; });
  const response = Response.json({}, { headers: { "X-Workspace-Version": "body-A-v1" } });
  response.json = async () => {
    startedBody();
    return new Promise<unknown>((resolve) => { finishBody = resolve; });
  };
  globalThis.fetch = async () => response;
  try {
    configureSession("body-A-v1");
    const pending = api.get("/leads");
    await bodyStarted;
    configureSession("body-B-v1");
    finishBody({ items: [{ title: "Old tenant result" }] });
    await assert.rejects(() => pending, (error) => error instanceof ApiError && error.code === "workspace_changed");
  } finally { globalThis.fetch = original; configureSession(null); }
});

test("HTTP errors retain actionable status without retrying a mutation", async () => {
  const original = globalThis.fetch;
  const cases = [
    { status: 404, body: { detail: "Lead not found" }, message: "Lead not found" },
    { status: 409, body: { detail: { code: "conflict", message: "The operation already exists" } }, message: "The operation already exists" },
    { status: 422, body: { detail: "Invalid request", errors: [{ loc: ["body", "email"], type: "value_error" }] }, message: "Please check these fields: email" },
    { status: 429, body: { detail: "Rate limit exceeded" }, message: "Rate limit exceeded" },
    { status: 503, body: { message: "The CRM could not complete this request.", code: "backend_error" }, message: "The CRM could not complete this request." },
  ];
  try {
    configureSession("errors-v1");
    for (const item of cases) {
      let calls = 0;
      globalThis.fetch = async () => { calls += 1; return Response.json(item.body, { status: item.status, headers: { "Retry-After": "7" } }); };
      await assert.rejects(() => api.post("/leads", { title: "A mutation" }), (error) => {
        assert.ok(error instanceof ApiError);
        assert.equal(error.status, item.status);
        assert.equal(error.message, item.message);
        assert.equal(error.retryAfter, 7);
        if (item.status === 422) assert.equal(error.fields?.email, "value error");
        return true;
      });
      assert.equal(calls, 1);
    }
  } finally { globalThis.fetch = original; configureSession(null); }
});

test("offline transport reports uncertainty once while external cancellation remains AbortError", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  try {
    configureSession("offline-v1");
    globalThis.fetch = async () => { calls += 1; throw new TypeError("Failed to fetch"); };
    await assert.rejects(() => api.post("/leads", { title: "Offline mutation" }), (error) => error instanceof ApiError && error.status === 0 && error.code === "network_error" && error.message.includes("Check the operation status"));
    assert.equal(calls, 1);
    globalThis.fetch = async (_input, init) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
    });
    const cancel = new AbortController();
    const pending = api.get("/leads", { signal: cancel.signal });
    cancel.abort();
    await assert.rejects(() => pending, (error) => error instanceof DOMException && error.name === "AbortError");
  } finally { globalThis.fetch = original; configureSession(null); }
});

test("client timeout cancels transport and gives an explicit non-replay error", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (_input, init) => new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
  });
  try {
    configureSession("timeout-test-v1");
    await assert.rejects(() => api.post("/leads", { title: "Timeout transport" }, { timeoutMs: 20 }), (error) => error instanceof ApiError && error.status === 408 && error.code === "timeout" && error.message.includes("Check the operation status"));
  } finally { globalThis.fetch = original; configureSession(null); }
});

test("production requires HTTPS and uses a host-only secure-cookie prefix", () => {
  const names = ["APP_ORIGIN", "BACKEND_API_URL", "FRONTEND_REDIS_URL", "SESSION_ENCRYPTION_KEY", "FRONTEND_ENV"] as const;
  const saved = Object.fromEntries(names.map((name) => [name, process.env[name]]));
  try {
    process.env.APP_ORIGIN = "https://crm.example.test";
    process.env.BACKEND_API_URL = "http://backend:8000";
    process.env.FRONTEND_REDIS_URL = "redis://127.0.0.1:6379/15";
    process.env.SESSION_ENCRYPTION_KEY = randomBytes(32).toString("hex");
    process.env.FRONTEND_ENV = "production";
    assert.equal(configuration().secure, true);
    assert.equal(cookieName(true), "__Host-globexa-session");
    process.env.APP_ORIGIN = "http://localhost:3000";
    assert.throws(() => configuration());
    process.env.FRONTEND_ENV = "testing";
    assert.equal(configuration().secure, false);
    process.env.BACKEND_API_URL = "http://backend:8000/api/v1";
    assert.throws(() => configuration());
  } finally { for (const name of names) { if (saved[name] === undefined) delete process.env[name]; else process.env[name] = saved[name]; } }
});
