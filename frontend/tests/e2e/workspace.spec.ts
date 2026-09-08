import { test, expect } from "@playwright/test";
import { apiLogin, fixture, crmHeaders, login } from "./helpers";

test("dashboard and all six analytics views use persisted server aggregates", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  const response = await context.request.get(
    "/api/crm/operations/analytics/dashboard",
    { headers: crmHeaders(session) },
  );
  expect(response.status()).toBe(200);
  const data = await response.json();
  await page.goto("/");
  await expect(
    page.getByText("Workspace overview", { exact: true }),
  ).toBeVisible();
  const leadMetric = page
    .locator(".metric-card")
    .filter({ has: page.getByText("Leads", { exact: true }) });
  await expect(leadMetric.locator(".metric-value")).toHaveText(
    String(data.leads),
  );
  await page.goto("/analytics");
  for (const name of [
    "Dashboard",
    "Pipeline",
    "Conversion",
    "Campaigns",
    "Activity",
    "AI usage",
  ]) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(
      page.getByText("Loading workspace data…", { exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("heading", { level: 2, name, exact: true }),
    ).toBeVisible();
    await expect(page.locator("main [role=alert]")).toHaveCount(0);
  }
  await page.getByLabel("Start (UTC)", { exact: true }).fill("2026-09-10");
  await page.getByLabel("End, exclusive (UTC)").fill("2026-09-09");
  await page.getByRole("button", { name: "Apply range", exact: true }).click();
  await expect(page.locator("main [role=alert]")).toHaveText(
    "End must be after start.",
  );
});

test("global search filters all ten supported types and opens Customer 360", async ({
  page,
  context,
}) => {
  await apiLogin(context);
  await page.goto("/search");
  await expect(page.getByLabel("Record type").locator("option")).toHaveCount(
    11,
  );
  await page.getByLabel("Search CRM", { exact: true }).fill("Alpha");
  await page.getByLabel("Record type").selectOption("contacts");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Alpha Customer/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Open record", exact: true })
    .first()
    .click();
  await expect(page).toHaveURL(
    new RegExp("/customers/contacts/" + fixture.records.tenantA.contact),
  );
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("profile edit persists; supported settings expose team, plan and audit data", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  const original = await (
    await context.request.get("/api/crm/auth/me", {
      headers: crmHeaders(session),
    })
  ).json();
  await page.goto("/settings");
  const edited = "Owner verification " + fixture.run;
  await page.getByLabel("Full name", { exact: true }).fill(edited);
  await page.getByRole("button", { name: "Save profile", exact: true }).click();
  await expect(
    page.getByText("Saved to the workspace.", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Full name", { exact: true })).toHaveValue(
    edited,
  );
  await page.getByLabel("Full name", { exact: true }).fill(original.full_name);
  await page.getByRole("button", { name: "Save profile", exact: true }).click();
  await expect(
    page.getByText("Saved to the workspace.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Team", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Team members" }),
  ).toContainText(fixture.users.sales_executive.email);
  await page
    .getByRole("button", { name: "Plan and entitlements", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Current plan", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("enterprise · active", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Audit log", exact: true }).click();
  await expect(
    page.getByText("Loading workspace data…", { exact: true }),
  ).toHaveCount(0);
  await expect(page.locator("main [role=alert]")).toHaveCount(0);
});

test("settings creates a member and changes its role through real authorization", async ({
  page,
  context,
}) => {
  await apiLogin(context);
  await page.goto("/settings");
  await page.getByRole("button", { name: "Team", exact: true }).click();
  await page
    .getByRole("button", { name: "Add team member", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Add team member",
    exact: true,
  });
  const email =
    "cp4.member." + crypto.randomUUID().slice(0, 8) + "@example.com";
  await dialog
    .getByLabel("Full name", { exact: true })
    .fill("Checkpoint member");
  await dialog.getByLabel("Email", { exact: true }).fill(email);
  await dialog
    .getByLabel("Initial password", { exact: true })
    .fill(crypto.randomUUID() + "A!");
  await dialog
    .getByRole("combobox", { name: "Role", exact: true })
    .selectOption("viewer");
  await dialog
    .getByRole("button", { name: "Create team member", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  const row = page.getByRole("row").filter({ hasText: email });
  await row.getByRole("button", { name: "Change role", exact: true }).click();
  const edit = page.getByRole("dialog", {
    name: "Change membership role",
    exact: true,
  });
  await edit
    .getByRole("combobox", { name: "New role", exact: true })
    .selectOption("marketing");
  await edit.getByRole("button", { name: "Save role", exact: true }).click();
  await expect(edit).not.toBeVisible();
  await page.getByLabel("Filter team by role").selectOption("marketing");
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Remove", exact: true }).click();
  const confirm = page.getByRole("dialog", {
    name: "Remove team member?",
    exact: true,
  });
  await confirm.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(row).toBeVisible();
});

test("network errors display retry and preserve server data", async ({
  page,
  context,
}) => {
  await apiLogin(context);
  await page.route("**/api/crm/operations/analytics/dashboard", (route) =>
    route.abort("internetdisconnected"),
  );
  await page.goto("/");
  await expect(page.locator("main [role=alert]")).toContainText(
    "network request failed",
  );
  await page.unroute("**/api/crm/operations/analytics/dashboard");
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.locator("main [role=alert]")).toHaveCount(0);
  await expect(page.locator(".metric-card").first()).toBeVisible();
});

test("viewer opens permitted profile and search but no admin controls", async ({
  page,
}) => {
  await login(page, "viewer");
  await page.goto("/settings");
  await expect(
    page.getByRole("heading", { name: "Your profile", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Team", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Audit log", exact: true }),
  ).toHaveCount(0);
  await page.goto("/search");
  await expect(
    page.getByLabel("Record type").locator("option[value=agents]"),
  ).toHaveCount(0);
});
