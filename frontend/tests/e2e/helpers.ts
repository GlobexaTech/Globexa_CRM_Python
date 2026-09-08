import { expect, type BrowserContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import type { Session } from "../../src/auth/types";

export type E2EFixture = { run: string; origin: string; backend: string; tenantA: string; tenantB: string; users: Record<string, { id: string; email: string; password: string }>; records: Record<string, Record<string, string>> };
export const fixture = JSON.parse(readFileSync(path.resolve(__dirname, "../../../evidence/fixture.json"), "utf8")) as E2EFixture;
export const crmHeaders = (session: Session) => ({ Origin: fixture.origin, "X-Workspace-Version": session.version });

export async function apiLogin(context: BrowserContext, role = "owner"): Promise<Session> {
  const user = fixture.users[role];
  const response = await context.request.post("/api/session", { headers: { Origin: fixture.origin }, data: { email: user.email, password: user.password } });
  expect(response.status()).toBe(200);
  return await response.json() as Session;
}

export async function login(page: Page, role = "owner") {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(fixture.users[role].email);
  await page.getByLabel("Password", { exact: true }).fill(fixture.users[role].password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(fixture.origin + "/");
}
