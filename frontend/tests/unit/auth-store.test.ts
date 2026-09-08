import { after, test } from "node:test";
import assert from "node:assert/strict";
import { randomBytes, randomUUID } from "node:crypto";
import { deleteSession, loadSession, newSessionId, redisClient, saveSession, type StoredSession, withSessionLock } from "../../src/auth/server/store";
import { sessionKey, SessionError } from "../../src/auth/server/security";

process.env.APP_ORIGIN ??= "http://127.0.0.1:3000";
process.env.BACKEND_API_URL ??= "http://127.0.0.1:8000";
process.env.FRONTEND_REDIS_URL ??= "redis://127.0.0.1:6379/15";
process.env.SESSION_ENCRYPTION_KEY ??= randomBytes(32).toString("hex");
process.env.FRONTEND_ENV ??= "testing";
const ids: string[] = [];
const id = () => { const value = newSessionId(); ids.push(value); return value; };
const value = (): StoredSession => ({
  public: { user: { id: randomUUID(), email: "user@example.test", full_name: "CRM User", first_name: "CRM", last_name: "User" }, tenant_id: randomUUID(), tenants: [], permissions: ["leads:read"], role: "sales_executive", version: randomUUID() },
  accessToken: randomBytes(32).toString("hex"), refreshToken: randomBytes(32).toString("hex"), expiresAt: Date.now() + 60000, absoluteExpiry: Date.now() + 120000,
});

after(async () => {
  const redis = await redisClient();
  for (const item of ids) await redis.del(sessionKey(item));
  await redis.quit();
});

test("real Redis stores encrypted sessions with a bounded TTL", async () => {
  const sessionId = id();
  const session = value();
  await saveSession(sessionId, session);
  assert.deepEqual(await loadSession(sessionId), session);
  const redis = await redisClient();
  assert.equal(redis.options?.commandOptions?.timeout, 3000);
  assert.equal(redis.options?.disableOfflineQueue, true);
  const raw = await redis.get(sessionKey(sessionId));
  assert.ok(raw && !raw.includes(session.accessToken) && !raw.includes(session.public.user.email));
  const ttl = await redis.ttl(sessionKey(sessionId));
  assert.ok(ttl > 0 && ttl <= 120);
});

test("tampered Redis records are deleted and fail closed", async () => {
  const sessionId = id();
  await saveSession(sessionId, value());
  await (await redisClient()).set(sessionKey(sessionId), "malformed-ciphertext", { EX: 60 });
  await assert.rejects(() => loadSession(sessionId), (error) => error instanceof SessionError && error.status === 401);
  assert.equal(await (await redisClient()).exists(sessionKey(sessionId)), 0);
});

test("logout deletion cannot be undone by an old refresh save", async () => {
  const sessionId = id();
  const session = value();
  await saveSession(sessionId, session);
  await deleteSession(sessionId);
  await assert.rejects(() => saveSession(sessionId, session, true), (error) => error instanceof SessionError && error.status === 401);
  await assert.rejects(() => loadSession(sessionId));
});

test("expired absolute sessions are rejected instead of extended", async () => {
  const session = value();
  session.absoluteExpiry = Date.now() - 1;
  await assert.rejects(() => saveSession(id(), session), (error) => error instanceof SessionError && error.status === 401);
});

test("real Redis locks serialize concurrent changes across callers", async () => {
  const sessionId = id();
  let concurrent = 0;
  let maxConcurrent = 0;
  let completed = 0;
  await Promise.all(Array.from({ length: 5 }, () => withSessionLock(sessionId, async () => {
    concurrent += 1;
    maxConcurrent = Math.max(maxConcurrent, concurrent);
    await new Promise((resolve) => setTimeout(resolve, 15));
    concurrent -= 1;
    completed += 1;
  })));
  assert.equal(completed, 5);
  assert.equal(maxConcurrent, 1);
  assert.equal(await (await redisClient()).exists(`${sessionKey(sessionId)}:lock`), 0);
});

test("failed work releases its Redis lock so a subsequent action can proceed", async () => {
  const sessionId = id();
  await assert.rejects(() => withSessionLock(sessionId, async () => { throw new Error("expected failure"); }));
  assert.equal(await withSessionLock(sessionId, async () => "next action"), "next action");
});
