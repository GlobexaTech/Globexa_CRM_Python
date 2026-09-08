import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, type Page, type APIRequestContext } from "@playwright/test";

type Fixture = {
  origin: string;
  backend: string;
  run: string;
  tenantA: string;
  tenantB: string;
  users: Record<string, { email: string; password: string; id: string }>;
  records: Record<"tenantA" | "tenantB", Record<string, string>>;
};
export const fixture = JSON.parse(
  readFileSync(
    resolve(process.env.CP4_FIXTURE_PATH ?? "../evidence/fixture.json"),
    "utf8",
  ),
) as Fixture;
export async function loginUI(page: Page, role = "owner") {
  await page.goto("/login");
  await page
    .getByLabel("Email address", { exact: true })
    .fill(fixture.users[role].email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(fixture.users[role].password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.locator(".session-state")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { level: 1, name: /Your business/ }),
  ).toBeVisible();
}
export async function backend(request: APIRequestContext, role = "owner") {
  const response = await request.post(`${fixture.backend}/api/v1/auth/login`, {
    form: {
      username: fixture.users[role].email,
      password: fixture.users[role].password,
    },
  });
  expect(response.ok(), `backend authentication (${role})`).toBeTruthy();
  const tokens = await response.json();
  const headers = {
    Authorization: `Bearer ${tokens.access_token}`,
    "X-Tenant-ID": fixture.tenantA,
  };
  return {
    get: (path: string) =>
      request.get(`${fixture.backend}/api/v1${path}`, { headers }),
    post: (path: string, data: unknown) =>
      request.post(`${fixture.backend}/api/v1${path}`, { headers, data }),
    patch: (path: string, data: unknown) =>
      request.patch(`${fixture.backend}/api/v1${path}`, { headers, data }),
    delete: (path: string) =>
      request.delete(`${fixture.backend}/api/v1${path}`, { headers }),
  };
}
export async function saved(
  page: Page,
  path: string,
  click: () => Promise<void>,
  method = "POST",
) {
  const waiting = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/crm${path}`) &&
      response.request().method() === method,
  );
  await click();
  const response = await waiting;
  if (!response.ok())
    throw new Error(
      `${method} ${path}: HTTP ${response.status()} ${await response.text()}`,
    );
  return response.status() === 204 ? null : response.json();
}
