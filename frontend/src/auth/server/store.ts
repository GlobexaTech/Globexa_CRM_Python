import { randomBytes, randomUUID } from "node:crypto";
import { createClient } from "redis";
import type { Session } from "../types";
import { configuration, seal, sessionKey, SessionError, unseal } from "./security";

export interface StoredSession {
  public: Session;
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  absoluteExpiry: number;
}

function makeClient() {
  return createClient({
    url: configuration().redis,
    socket: { connectTimeout: 3000, reconnectStrategy: false },
    commandOptions: { timeout: 3000 },
    disableOfflineQueue: true,
    commandsQueueMaxLength: 1000,
  });
}
type RedisClient = ReturnType<typeof makeClient>;
let connection: Promise<RedisClient> | undefined;

export function redisClient(): Promise<RedisClient> {
  if (!connection) {
    connection = (async () => {
      const redis = makeClient();
      // Never log connection URLs, session values or request bodies.
      redis.on("error", () => {});
      redis.on("end", () => { connection = undefined; });
      await redis.connect();
      return redis;
    })().catch((error) => { connection = undefined; throw error; });
  }
  return connection;
}

export function newSessionId() { return randomBytes(32).toString("hex"); }

export async function loadSession(id: string): Promise<StoredSession> {
  const redis = await redisClient();
  const key = sessionKey(id);
  const encrypted = await redis.get(key);
  if (!encrypted) throw new SessionError(401, "session_expired", "Please sign in again.");
  try {
    const session = unseal<StoredSession>(encrypted, configuration().key);
    if (session.absoluteExpiry <= Date.now()) throw new Error("Expired session");
    return session;
  } catch {
    await redis.del(key);
    throw new SessionError(401, "session_expired", "Please sign in again.");
  }
}

export async function saveSession(id: string, session: StoredSession, existingOnly = false) {
  const ttl = Math.ceil((session.absoluteExpiry - Date.now()) / 1000);
  if (ttl <= 0) throw new SessionError(401, "session_expired", "Please sign in again.");
  const redis = await redisClient();
  const result = await redis.set(sessionKey(id), seal(session, configuration().key), { EX: ttl, ...(existingOnly ? { XX: true } : {}) });
  if (result !== "OK") throw new SessionError(401, "session_expired", "Please sign in again.");
}

export async function deleteSession(id: string) {
  await (await redisClient()).del(sessionKey(id));
}

/** Serializes refresh, mutations and tenant transitions across every frontend instance. */
export async function withSessionLock<T>(id: string, run: () => Promise<T>): Promise<T> {
  const redis = await redisClient();
  const key = `${sessionKey(id)}:lock`;
  const owner = randomUUID();
  const deadline = Date.now() + 16000;
  while (await redis.set(key, owner, { NX: true, PX: 60000 }) !== "OK") {
    if (Date.now() >= deadline) throw new SessionError(503, "session_busy", "The session is busy. Please retry shortly.", "2");
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  try { return await run(); }
  finally {
    await redis.eval("if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end", { keys: [key], arguments: [owner] });
  }
}
