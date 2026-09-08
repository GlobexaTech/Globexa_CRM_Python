import { test, expect, type BrowserContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { createHmac, randomBytes } from "node:crypto";
import { createClient } from "redis";
import { seal, sessionKey, unseal } from "../../src/auth/server/security";
import type { Session } from "../../src/auth/types";
import type { StoredSession } from "../../src/auth/server/store";

type Fixture = { origin: string; backend: string; tenantA: string; tenantB: string; users: Record<string, { id: string; email: string; password: string }>; records: Record<string, Record<string, string>> };
const fixture = JSON.parse(readFileSync(path.resolve(__dirname, "../../../evidence/fixture.json"), "utf8")) as Fixture;
const runtime = JSON.parse(readFileSync(path.resolve(__dirname, "../../../evidence/runtime.env.json"), "utf8")) as Record<string, string>;

async function signIn(context: BrowserContext, role = "owner"): Promise<Session> {
  const user = fixture.users[role];
  const response = await context.request.post("/api/session", { headers: { Origin: fixture.origin }, data: { email: user.email, password: user.password } });
  expect(response.status()).toBe(200);
  return await response.json() as Session;
}

async function signInUi(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(fixture.users.owner.email);
  await page.getByLabel("Password", { exact: true }).fill(fixture.users.owner.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(fixture.origin + "/");
}

async function updateStoredSession(context: BrowserContext, update: (value: StoredSession) => void) {
  const cookie = (await context.cookies()).find((item) => item.name === "globexa-test-session");
  expect(Boolean(cookie)).toBe(true);
  const redis = createClient({ url: runtime.FRONTEND_REDIS_URL });
  await redis.connect();
  try {
    const key = sessionKey(cookie!.value);
    const encrypted = await redis.get(key);
    expect(Boolean(encrypted)).toBe(true);
    const value = unseal<StoredSession>(encrypted!, Buffer.from(runtime.SESSION_ENCRYPTION_KEY, "hex"));
    update(value);
    await redis.set(key, seal(value, Buffer.from(runtime.SESSION_ENCRYPTION_KEY, "hex")), { KEEPTTL: true });
  } finally { await redis.quit(); }
}

test("protected page requires sign in and invalid credentials stay signed out", async ({ page, context }) => {
  await page.goto("/leads");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Email address").fill(fixture.users.owner.email);
  await page.getByLabel("Password", { exact: true }).fill("incorrect-e2e-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Email or password is incorrect" })).toBeVisible();
  expect((await context.request.get("/api/session")).status()).toBe(401);
});

test("real login restores on reload and browser receives no backend credentials", async ({ page, context }) => {
  await signInUi(page);
  await page.reload();
  await expect(page.getByRole("heading", { name: /welcome|dashboard|overview/i }).first()).toBeVisible();
  const response = await context.request.get("/api/session");
  expect(response.status()).toBe(200);
  const value = await response.json() as Session;
  expect(value.user.id).toBe(fixture.users.owner.id);
  expect(value.tenant_id).toBe(fixture.tenantA);
  expect(value.tenants).toHaveLength(2);
  const publicText = JSON.stringify(value);
  expect(/access_token|refresh_token|client_secret|hashed_password|api_key/.test(publicText)).toBe(false);
  const cookie = (await context.cookies()).find((item) => item.name === "globexa-test-session");
  expect(Boolean(cookie?.httpOnly)).toBe(true);
  expect(cookie?.sameSite).toBe("Lax");
  expect(/^[a-f\d]{64}$/.test(cookie?.value ?? "")).toBe(true);
  const storage = await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage }, cookies: document.cookie }));
  expect(/access_token|refresh_token|globexa-test-session|Bearer /.test(JSON.stringify(storage))).toBe(false);
});

test("expired access token refreshes through the real backend exactly within the session", async ({ context }) => {
  const before = await signIn(context);
  await updateStoredSession(context, (stored) => {
    const [header, encoded] = stored.accessToken.split(".");
    const claims = JSON.parse(Buffer.from(encoded, "base64url").toString("utf8"));
    claims.exp = Math.floor(Date.now() / 1000) - 60;
    const payload = Buffer.from(JSON.stringify(claims)).toString("base64url");
    const signature = createHmac("sha256", runtime.SECURITY_SECRET_KEY).update(`${header}.${payload}`).digest("base64url");
    stored.accessToken = `${header}.${payload}.${signature}`;
    stored.expiresAt = 0;
  });
  const response = await context.request.get("/api/session");
  expect(response.status()).toBe(200);
  const after = await response.json() as Session;
  expect(after.user.id).toBe(before.user.id);
  expect(after.tenant_id).toBe(before.tenant_id);
  expect(after.version).toBe(before.version);
  expect((await context.request.get("/api/crm/leads", { headers: { "X-Workspace-Version": after.version } })).status()).toBe(200);
});

test("invalid refresh token destroys the server session and cannot loop", async ({ context }) => {
  await signIn(context);
  await updateStoredSession(context, (stored) => { stored.refreshToken = randomBytes(32).toString("hex"); stored.expiresAt = 0; });
  expect((await context.request.get("/api/session")).status()).toBe(401);
  expect((await context.request.get("/api/session")).status()).toBe(401);
});

test("logout deletes the server session and rejects reuse of the old opaque cookie", async ({ context }) => {
  const session = await signIn(context);
  const cookie = (await context.cookies()).find((item) => item.name === "globexa-test-session")!;
  const response = await context.request.delete("/api/session", { headers: { Origin: fixture.origin } });
  expect(response.status()).toBe(204);
  expect((await context.request.get("/api/session")).status()).toBe(401);
  await context.addCookies([cookie]);
  expect((await context.request.get("/api/crm/leads", { headers: { "X-Workspace-Version": session.version } })).status()).toBe(401);
});

test("session and CRM mutations reject foreign origins", async ({ context }) => {
  const session = await signIn(context);
  expect((await context.request.delete("/api/session", { headers: { Origin: "https://other.example.test" } })).status()).toBe(403);
  expect((await context.request.post("/api/crm/leads", { headers: { Origin: "https://other.example.test", "X-Workspace-Version": session.version }, data: { title: "Should not exist" } })).status()).toBe(403);
  expect((await context.request.get("/api/session")).status()).toBe(200);
});

test("tenant switch issues a new workspace version and blocks stale reads and writes", async ({ context }) => {
  const before = await signIn(context);
  const changed = await context.request.post("/api/session/tenant", { headers: { Origin: fixture.origin, "X-Workspace-Version": before.version }, data: { tenant_id: fixture.tenantB } });
  expect(changed.status()).toBe(200);
  const after = await changed.json() as Session;
  expect(after.tenant_id).toBe(fixture.tenantB);
  expect(after.version === before.version).toBe(false);
  const staleRead = await context.request.get("/api/crm/leads", { headers: { "X-Workspace-Version": before.version } });
  expect(staleRead.status()).toBe(409);
  const staleWrite = await context.request.post("/api/crm/leads", { headers: { Origin: fixture.origin, "X-Workspace-Version": before.version }, data: { title: "Stale mutation must not be saved" } });
  expect(staleWrite.status()).toBe(409);
  const response = await context.request.get("/api/crm/leads", { headers: { "X-Workspace-Version": after.version } });
  expect(response.status()).toBe(200);
  const text = await response.text();
  expect(text.includes(fixture.records.tenantB.lead)).toBe(true);
  expect(text.includes(fixture.records.tenantA.lead)).toBe(false);
  expect((await context.request.get(`/api/crm/leads/${fixture.records.tenantA.lead}`, { headers: { "X-Workspace-Version": after.version } })).status()).toBe(404);
});

test("manually supplied workspace IDs and auth token proxy paths are rejected", async ({ context }) => {
  const session = await signIn(context, "viewer");
  expect((await context.request.post("/api/session/tenant", { headers: { Origin: fixture.origin, "X-Workspace-Version": session.version }, data: { tenant_id: fixture.tenantB } })).status()).toBe(403);
  expect((await context.request.get(`/api/crm/leads?tenant_id=${fixture.tenantB}`, { headers: { "X-Workspace-Version": session.version } })).status()).toBe(400);
  expect((await context.request.post("/api/crm/auth/refresh", { headers: { Origin: fixture.origin, "X-Workspace-Version": session.version }, data: {} })).status()).toBe(404);
});

test("browser workspace switch clears old records and open drawers across tabs", async ({ page, context }) => {
  await signIn(context);
  const titleA = fixture.records.tenantA.leadTitle;
  const titleB = fixture.records.tenantB.leadTitle;
  const leadSearch = "Search lead titles and descriptions…";
  await page.goto("/leads");
  await page.getByPlaceholder(leadSearch).fill(titleA);
  await expect(page.getByRole("button", { name: titleA, exact: true })).toBeVisible();
  const second = await context.newPage();
  try {
    await second.goto("/leads");
    await second.getByPlaceholder(leadSearch).fill(titleA);
    await second.getByRole("button", { name: titleA, exact: true }).click();
    await expect(second.getByRole("dialog", { name: titleA, exact: true })).toBeVisible();
    const switched = page.waitForResponse((response) => response.url().endsWith("/api/session/tenant") && response.request().method() === "POST");
    await page.getByRole("combobox", { name: "Workspace", exact: true }).selectOption(fixture.tenantB);
    expect((await switched).status()).toBe(200);
    await expect(page).toHaveURL(fixture.origin + "/");
    await expect(second.getByRole("dialog", { name: titleA, exact: true })).toHaveCount(0);
    await expect(second.getByRole("combobox", { name: "Workspace", exact: true })).toHaveValue(fixture.tenantB);
    await expect(second.getByPlaceholder(leadSearch)).toHaveValue("");
    await expect(second.getByRole("button", { name: titleB, exact: true })).toBeVisible();
    await expect(second.getByRole("button", { name: titleA, exact: true })).toHaveCount(0);
    await page.goto("/leads");
    await expect(page.getByRole("button", { name: titleB, exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: titleA, exact: true })).toHaveCount(0);
    await page.getByRole("combobox", { name: "Workspace", exact: true }).selectOption(fixture.tenantA);
    await expect(page).toHaveURL(fixture.origin + "/");
    await page.goto("/leads");
    await expect(page.getByRole("button", { name: titleA, exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: titleB, exact: true })).toHaveCount(0);
  } finally { await second.close(); }
});

test("real missing-record and backend validation errors remain visible and preserve form input", async ({ page, context }) => {
  await signIn(context);
  const missing = "00000000-0000-4000-8000-000000000004";
  const notFound = page.waitForResponse((response) => response.url().includes(`/operations/customers/leads/${missing}`));
  await page.goto(`/customers/leads/${missing}`);
  expect((await notFound).status()).toBe(404);
  await expect(page.getByRole("alert").filter({ hasText: /not found/i })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again", exact: true })).toBeVisible();
  await page.goto("/contacts");
  await page.getByRole("button", { name: "New Contact", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("First name", { exact: true }).fill("Validation");
  await dialog.getByLabel("Last name", { exact: true }).fill("Preserved");
  // Browser accepts this syntactic address; authoritative backend EmailStr
  // rejects its reserved domain, so this exercises the actual 422 response.
  await dialog.getByLabel("Email", { exact: true }).fill("validation@example.test");
  const rejected = page.waitForResponse((response) => response.url().endsWith("/api/crm/contacts") && response.request().method() === "POST");
  await dialog.getByRole("button", { name: "Create contact", exact: true }).click();
  expect((await rejected).status()).toBe(422);
  await expect(dialog.getByRole("alert")).toContainText("email");
  await expect(dialog.getByLabel("First name", { exact: true })).toHaveValue("Validation");
  await expect(dialog.getByLabel("Email", { exact: true })).toHaveValue("validation@example.test");
});

test("offline query shows an actionable error and succeeds when retried after reconnecting", async ({ page, context }) => {
  await signIn(context);
  await page.goto("/leads");
  await expect(page.getByRole("button", { name: fixture.records.tenantA.leadTitle, exact: true })).toBeVisible();
  try {
    await context.setOffline(true);
    await page.getByPlaceholder("Search lead titles and descriptions…").fill(fixture.records.tenantA.leadTitle);
    await expect(page.getByRole("alert").filter({ hasText: "The network request failed" })).toBeVisible();
    await page.getByRole("button", { name: "Try again", exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: "The network request failed" })).toBeVisible();
    await context.setOffline(false);
    await page.getByRole("button", { name: "Try again", exact: true }).click();
    await expect(page.getByRole("button", { name: fixture.records.tenantA.leadTitle, exact: true })).toBeVisible();
    await expect(page.getByRole("alert").filter({ hasText: "The network request failed" })).toHaveCount(0);
  } finally { await context.setOffline(false); }
});

for (const role of ["owner", "admin", "sales_manager", "sales_executive", "marketing", "viewer", "ai_agent"]) {
  test(`real ${role} permissions match backend authorization`, async ({ context }) => {
    const session = await signIn(context, role);
    expect(session.role).toBe(role);
    expect(session.permissions.includes("leads:read")).toBe(true);
    const mayWrite = ["owner", "admin", "sales_manager", "sales_executive", "marketing"].includes(role);
    expect(session.permissions.includes("leads:write")).toBe(mayWrite);
    const response = await context.request.post("/api/crm/leads", { headers: { Origin: fixture.origin, "X-Workspace-Version": session.version }, data: { title: `E2E role authorization ${role}` } });
    expect(response.status()).toBe(mayWrite ? 201 : 403);
  });
}
