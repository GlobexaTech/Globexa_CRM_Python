import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { randomUUID } from "node:crypto";
import { apiLogin, crmHeaders, fixture } from "./helpers";

test("advanced builder persists publishes simulates and executes a real workflow", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  await page.goto("/automations/advanced");
  await page
    .getByRole("button", { name: "New advanced workflow", exact: true })
    .click();
  const name = `Advanced notification ${randomUUID()}`;
  await page.getByLabel("Workflow name", { exact: true }).fill(name);
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/crm/automation/workflows") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  const response = await created;
  expect(response.status()).toBe(201);
  const workflow = await response.json();
  const selected = page.getByRole("region", { name: "Selected workflow" });
  await expect(
    selected.getByRole("heading", { name, exact: true }),
  ).toBeVisible();
  await selected
    .getByRole("button", { name: "Run dry test", exact: true })
    .click();
  await expect(
    selected.getByText('"dry_run": true', { exact: false }),
  ).toBeVisible();
  const published = page.waitForResponse((response) =>
    response.url().endsWith(`/automation/workflows/${workflow.id}/publish`),
  );
  await selected
    .getByRole("button", { name: "Publish version", exact: true })
    .click();
  expect((await published).status()).toBe(200);
  const queued = page.waitForResponse((response) =>
    response.url().endsWith(`/automation/workflows/${workflow.id}/execute`),
  );
  await selected
    .getByRole("button", { name: "Start execution", exact: true })
    .click();
  const queuedResponse = await queued;
  expect(queuedResponse.status()).toBe(202);
  const execution = await queuedResponse.json();
  await expect
    .poll(
      async () => {
        const detail = await context.request.get(
          `/api/crm/automation/executions/${execution.id}`,
          { headers: crmHeaders(session) },
        );
        expect(detail.status()).toBe(200);
        return (await detail.json()).state;
      },
      { timeout: 45000 },
    )
    .toBe("COMPLETED");
  await selected
    .getByRole("button", { name: "Refresh timeline", exact: true })
    .click();
  await expect(
    selected.getByText("step_1 · COMPLETED", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: `Open ${name}`, exact: true }).click();
  await expect(
    page
      .getByRole("region", { name: "Selected workflow" })
      .getByText("ACTIVE · Version 1", { exact: true }),
  ).toBeVisible();
});

test("advanced automation API rejects viewer mutations and foreign tenant access", async ({
  context,
  browser,
}) => {
  const owner = await apiLogin(context);
  const created = await context.request.post("/api/crm/automation/workflows", {
    headers: crmHeaders(owner),
    data: {
      name: `Private ${randomUUID()}`,
      definition: {
        trigger: "manual",
        nodes: [
          {
            id: "notice",
            type: "action",
            action: "create_notification",
            arguments: { message: "Tenant private notice" },
          },
        ],
      },
    },
  });
  expect(created.status()).toBe(201);
  const workflow = await created.json();
  const viewerContext = await browser.newContext({
    baseURL: test.info().project.use.baseURL,
  });
  const otherContext = await browser.newContext({
    baseURL: test.info().project.use.baseURL,
  });
  try {
    const viewer = await apiLogin(viewerContext, "viewer");
    expect(
      (
        await viewerContext.request.post(
          `/api/crm/automation/workflows/${workflow.id}/publish`,
          { headers: crmHeaders(viewer), data: {} },
        )
      ).status(),
    ).toBe(403);
    const otherOwner = await apiLogin(otherContext);
    const switched = await otherContext.request.post("/api/session/tenant", {
      headers: crmHeaders(otherOwner),
      data: { tenant_id: fixture.tenantB },
    });
    expect(switched.status()).toBe(200);
    const other = await switched.json();
    expect(
      (
        await otherContext.request.get(
          `/api/crm/automation/workflows/${workflow.id}`,
          { headers: crmHeaders(other) },
        )
      ).status(),
    ).toBe(404);
  } finally {
    await viewerContext.close();
    await otherContext.close();
  }
});

for (const width of [1440, 1280, 768, 390]) {
  test(`advanced workflow screen accessibility at ${width}`, async ({
    page,
    context,
  }) => {
    await apiLogin(context);
    await page.setViewportSize({ width, height: 960 });
    await page.goto("/automations/advanced");
    await expect(
      page.getByRole("heading", {
        level: 1,
        name: "Advanced workflows",
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "New advanced workflow", exact: true })
      .click();
    await expect(
      page.getByLabel("Workflow name", { exact: true }),
    ).toBeVisible();
    const scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(scan.violations).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    await page.screenshot({
      path: test.info().outputPath(`automation-advanced-${width}.png`),
      fullPage: true,
    });
  });
}
