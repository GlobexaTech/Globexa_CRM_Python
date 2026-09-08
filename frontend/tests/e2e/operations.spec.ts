import { test, expect, type Page, type Locator } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { apiLogin, crmHeaders, fixture } from "./helpers";
import type { Session } from "../../src/auth/types";

const seed = fixture.records.tenantA;
async function bodyOf<T>(
  page: Page,
  session: Session,
  endpoint: string,
): Promise<T> {
  const result = await page.request.get("/api/crm" + endpoint, {
    headers: crmHeaders(session),
  });
  expect(result.ok()).toBe(true);
  return result.json() as Promise<T>;
}
async function confirm(page: Page, title: string, button: string) {
  await page
    .getByRole("dialog", { name: title, exact: true })
    .getByRole("button", { name: button, exact: true })
    .click();
}
async function createConversation(page: Page, subject: string) {
  await page.goto("/conversations");
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "New conversation",
    exact: true,
  });
  await dialog.getByLabel("Subject", { exact: true }).fill(subject);
  await dialog.getByLabel("Participant email").fill(seed.contactEmail);
  await dialog.getByLabel("Email integration").selectOption(seed.integration);
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/crm/operations/conversations") &&
      r.request().method() === "POST",
  );
  await dialog
    .getByRole("button", { name: "Create conversation", exact: true })
    .click();
  const result = await response;
  expect(result.status()).toBe(201);
  return (await result.json()).id as string;
}
async function queueMessage(page: Page, text: string) {
  await page
    .getByLabel("Recipient email", { exact: true })
    .fill(seed.contactEmail);
  await page.getByLabel("Message", { exact: true }).fill(text);
  const response = page.waitForResponse(
    (r) =>
      /\/operations\/conversations\/[^/]+\/messages$/.test(r.url()) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue message", exact: true })
    .click();
  const result = await response;
  expect(result.status()).toBe(202);
  expect(result.request().headers()["idempotency-key"]).toMatch(
    /^[a-f\d-]{36}$/,
  );
  return (await result.json()).id as string;
}
async function createCampaign(page: Page, name: string) {
  await page.goto("/campaigns");
  await page.getByRole("button", { name: "New campaign", exact: true }).click();
  const dialog = page.getByRole("dialog", {
    name: "Create campaign",
    exact: true,
  });
  await dialog.getByLabel("Campaign name").fill(name);
  await dialog.getByLabel("Sender name").fill("Globexa E2E");
  await dialog.getByLabel("Sender email").fill("sender@example.com");
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/crm/campaigns") && r.request().method() === "POST",
  );
  await dialog
    .getByRole("button", { name: "Create draft", exact: true })
    .click();
  const result = await response;
  expect(result.status()).toBe(201);
  return (await result.json()).id as string;
}
async function planCampaign(dialog: Locator, trigger = "") {
  await dialog
    .getByRole("button", { name: "Configure audience and messages" })
    .click();
  await dialog
    .getByLabel("Connected email integration")
    .selectOption(seed.integration);
  await dialog
    .getByRole("checkbox", {
      name: new RegExp(seed.contactEmail.replaceAll(".", "\\.")),
    })
    .check();
  await dialog
    .getByLabel("First message subject")
    .fill("Verified campaign subject");
  await dialog
    .getByLabel("First message body")
    .fill("A reviewable message for the external test provider.");
  if (trigger)
    await dialog.getByLabel("Campaign trigger").selectOption(trigger);
  await dialog
    .getByRole("button", { name: "Save delivery plan", exact: true })
    .click();
  await expect(
    dialog.getByRole("status").filter({
      hasText:
        /Audience and message plan saved|Recipient delivery is tracked separately/,
    }),
  ).toContainText("Audience and message plan saved");
}

test("conversation sends use durable jobs, provider IDs and mobile list/detail navigation", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/conversations?conversation=" + seed.conversation);
  await expect(
    page.getByRole("heading", {
      name: "Alpha customer conversation",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Mark as read" }).click();
  const text = "Verified mobile conversation " + randomUUID();
  const job = await queueMessage(page, text);
  await expect
    .poll(
      async () =>
        (
          await bodyOf<{ status: string }>(
            page,
            session,
            "/operations/jobs/" + job,
          )
        ).status,
      { timeout: 30000 },
    )
    .toBe("completed");
  await expect(page.getByText(text, { exact: true })).toBeVisible();
  const messages = await bodyOf<{
    items: { body: string; provider_message_id: string; status: string }[];
  }>(
    page,
    session,
    `/operations/conversations/${seed.conversation}/messages?limit=100`,
  );
  const actual = messages.items.filter((message) => message.body === text);
  expect(actual).toHaveLength(1);
  expect(actual[0].status).toBe("sent");
  expect(actual[0].provider_message_id).toMatch(/^fixture-/);
  await page
    .getByRole("button", { name: "Conversation list", exact: true })
    .click();
  await expect(page.getByLabel("Search conversations")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

for (const scenario of [
  { marker: "provider-failure", state: "failed" },
  { marker: "provider-unknown", state: "unknown" },
]) {
  test(`conversation displays actual ${scenario.state} provider outcome without automatic resend`, async ({
    page,
    context,
  }) => {
    const session = await apiLogin(context);
    const conversation = await createConversation(
      page,
      `[${scenario.marker}] ${randomUUID()}`,
    );
    const job = await queueMessage(page, "Test external provider outcome");
    await expect
      .poll(
        async () =>
          (
            await bodyOf<{ status: string }>(
              page,
              session,
              "/operations/jobs/" + job,
            )
          ).status,
        { timeout: 30000 },
      )
      .toBe(scenario.state);
    await expect(
      page.getByText(`Operation: ${scenario.state}`, { exact: true }),
    ).toBeVisible();
    if (scenario.state === "unknown")
      await expect(
        page.getByText(/Delivery status pending verification/).first(),
      ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Retry operation" }),
    ).toHaveCount(0);
    const messages = await bodyOf<{
      items: {
        direction: string;
        status: string;
        provider_message_id: string | null;
      }[];
    }>(page, session, `/operations/conversations/${conversation}/messages`);
    const outbound = messages.items.filter(
      (item) => item.direction === "outbound",
    );
    expect(outbound).toHaveLength(1);
    expect(outbound[0].status).toBe(scenario.state);
    expect(outbound[0].provider_message_id).toBeNull();
  });
}

test("campaign create, audience, UTC schedule, pause, resume, launch and cancellation persist", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  const id = await createCampaign(page, "Lifecycle " + randomUUID());
  const dialog = page.getByRole("dialog", {
    name: "Campaign details",
    exact: true,
  });
  await planCampaign(dialog, "contact.created");
  const schedule = new Date(Date.now() + 3600000);
  const local = new Date(
    schedule.getTime() - schedule.getTimezoneOffset() * 60000,
  )
    .toISOString()
    .slice(0, 16);
  await dialog.getByLabel("Schedule in your local timezone").fill(local);
  await dialog
    .getByRole("button", { name: "Schedule campaign", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (await bodyOf<{ status: string }>(page, session, "/campaigns/" + id))
          .status,
    )
    .toBe("scheduled");
  await dialog
    .getByRole("button", { name: "Pause campaign", exact: true })
    .click();
  await expect(
    dialog.getByRole("button", { name: "Resume campaign", exact: true }),
  ).toBeVisible();
  await dialog
    .getByRole("button", { name: "Resume campaign", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Launch campaign", exact: true })
    .click();
  await confirm(page, "Launch campaign?", "Launch campaign");
  await expect
    .poll(
      async () =>
        (await bodyOf<{ status: string }>(page, session, "/campaigns/" + id))
          .status,
    )
    .toBe("sending");
  await expect(
    dialog.getByRole("status").filter({
      hasText:
        /Audience and message plan saved|Recipient delivery is tracked separately/,
    }),
  ).toContainText("Recipient delivery is tracked separately");
  await dialog
    .getByRole("button", { name: "Pause campaign", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Resume campaign", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Cancel campaign", exact: true })
    .click();
  await confirm(page, "Cancel campaign?", "Cancel campaign");
  await expect
    .poll(
      async () =>
        (await bodyOf<{ status: string }>(page, session, "/campaigns/" + id))
          .status,
    )
    .toBe("cancelled");
});

test("campaign delivery records real sent and suppressed outcomes and unsubscribe handling", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  const unique = randomUUID();
  const contact = await context.request.post("/api/crm/contacts", {
    headers: crmHeaders(session),
    data: {
      first_name: "Suppressed",
      last_name: unique,
      email: unique + "@example.com",
      email_opted_out: true,
    },
  });
  expect(contact.status()).toBe(201);
  const id = await createCampaign(page, "Delivery " + unique);
  const dialog = page.getByRole("dialog", {
    name: "Campaign details",
    exact: true,
  });
  await dialog
    .getByRole("button", { name: "Configure audience and messages" })
    .click();
  await dialog
    .getByLabel("Connected email integration")
    .selectOption(seed.integration);
  await dialog
    .getByRole("checkbox", {
      name: new RegExp(seed.contactEmail.replaceAll(".", "\\.")),
    })
    .check();
  await dialog.getByRole("checkbox", { name: new RegExp(unique) }).check();
  await dialog.getByLabel("First message subject").fill("Suppression test");
  await dialog
    .getByLabel("First message body")
    .fill("Test provider delivery, with signed backend unsubscribe.");
  await dialog.getByRole("button", { name: "Save delivery plan" }).click();
  await expect(
    dialog.getByRole("status").filter({
      hasText:
        /Audience and message plan saved|Recipient delivery is tracked separately/,
    }),
  ).toContainText("Audience and message plan saved");
  await dialog
    .getByRole("button", { name: "Launch campaign", exact: true })
    .click();
  await confirm(page, "Launch campaign?", "Launch campaign");
  await expect
    .poll(
      async () => {
        const stats = await bodyOf<{ sent: number; suppressed: number }>(
          page,
          session,
          `/operations/campaigns/${id}/statistics`,
        );
        return [stats.sent, stats.suppressed];
      },
      { timeout: 30000 },
    )
    .toEqual([1, 1]);
  await dialog
    .getByRole("button", { name: "Refresh status", exact: true })
    .click();
  await expect(
    dialog.getByText("suppressed", { exact: false }).first(),
  ).toBeVisible();
  const outcomes = await bodyOf<{ items: { status: string }[] }>(
    page,
    session,
    `/campaigns/${id}/recipients`,
  );
  expect(outcomes.items.map((item) => item.status).sort()).toEqual([
    "sent",
    "suppressed",
  ]);
  const conversations = await bodyOf<{
    items: { id: string; subject: string }[];
  }>(page, session, "/operations/conversations?q=Suppression%20test");
  expect(conversations.items.length).toBeGreaterThan(0);
  const messages = await bodyOf<{ items: { body: string }[] }>(
    page,
    session,
    `/operations/conversations/${conversations.items[0].id}/messages`,
  );
  expect(
    messages.items.some((item) =>
      item.body.includes("/api/v1/unsubscribe?token="),
    ),
  ).toBe(true);
});

test("workflow definition versions, enabled state and real event execution create a related task", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  const name = "Workflow " + randomUUID();
  const taskTitle = "Automation follow-up " + randomUUID();
  await page.goto("/automations");
  await page.getByRole("button", { name: "New workflow" }).click();
  let dialog = page.getByRole("dialog", {
    name: "Create workflow",
    exact: true,
  });
  await dialog.getByLabel("Workflow name").fill(name);
  await dialog.getByLabel("title (required)", { exact: true }).fill(taskTitle);
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/crm/operations/workflows") &&
      r.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "Save disabled workflow" }).click();
  const id = (await (await response).json()).id as string;
  dialog = page.getByRole("dialog", { name: "Workflow details", exact: true });
  await dialog
    .getByRole("button", { name: "Enable workflow", exact: true })
    .click();
  await expect(
    dialog.getByRole("button", { name: "Disable workflow", exact: true }),
  ).toBeVisible();
  await page.goto("/leads");
  await page.getByRole("button", { name: "New Lead", exact: true }).click();
  const leadDialog = page.getByRole("dialog", {
    name: "New lead",
    exact: true,
  });
  await leadDialog
    .getByLabel("Lead title", { exact: true })
    .fill("Triggered " + randomUUID());
  await leadDialog
    .getByRole("button", { name: "Create lead", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (
          await bodyOf<{ items: { status: string }[] }>(
            page,
            session,
            `/operations/workflows/${id}/executions`,
          )
        ).items.some((log) => log.status === "completed"),
      { timeout: 30000 },
    )
    .toBe(true);
  const tasks = await bodyOf<{ items: { title: string; lead_id: string }[] }>(
    page,
    session,
    "/tasks?page_size=100",
  );
  expect(
    tasks.items.some((task) => task.title === taskTitle && task.lead_id),
  ).toBe(true);
  await page.goto("/automations");
  await page
    .locator("article")
    .filter({ has: page.getByRole("heading", { name, exact: true }) })
    .getByRole("button")
    .click();
  dialog = page.getByRole("dialog", { name: "Workflow details", exact: true });
  await expect(
    dialog.getByText("completed", { exact: true }).first(),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Edit definition" }).click();
  await dialog.getByLabel("Workflow name").fill(name + " revised");
  await dialog.getByRole("button", { name: "Save disabled workflow" }).click();
  const updated = await bodyOf<{ version: number; enabled: boolean }>(
    page,
    session,
    "/operations/workflows/" + id,
  );
  expect(updated.version).toBe(2);
  expect(updated.enabled).toBe(false);
});

test("provider capabilities, OAuth callback, refresh, sync history and disconnect remain backend authoritative", async ({
  page,
  context,
}) => {
  await apiLogin(context);
  await page.goto("/integrations");
  await expect(
    page.getByText("Not available in this release", { exact: true }),
  ).toHaveCount(6);
  const name = "OAuth E2E " + randomUUID();
  await page.getByRole("button", { name: "Add gmail integration" }).click();
  const dialog = page.getByRole("dialog", {
    name: "Add gmail integration",
    exact: true,
  });
  await dialog.getByLabel("Connection name").fill(name);
  await dialog.getByRole("button", { name: "Create integration" }).click();
  let card = page
    .locator("article")
    .filter({ has: page.getByRole("heading", { name, exact: true }) });
  await expect(card.getByText("pending", { exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Authorize", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "backend confirmed the integration is connected",
  );
  expect(new URL(page.url()).search).toBe("");
  expect(
    await page.evaluate(() =>
      sessionStorage.getItem("globexa-oauth-correlation"),
    ),
  ).toBeNull();
  await page.getByRole("link", { name: "Return to Integrations" }).click();
  card = page
    .locator("article")
    .filter({ has: page.getByRole("heading", { name, exact: true }) });
  await card.getByRole("button", { name: "Refresh credentials" }).click();
  await expect(card.getByRole("status")).toContainText("credentials are valid");
  await card.getByRole("button", { name: "Queue sync", exact: true }).click();
  await expect(
    card.getByText("Operation: completed", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await card.getByRole("button", { name: "Sync history", exact: true }).click();
  await expect(
    card.getByRole("heading", { name: "Sync history" }),
  ).toBeVisible();
  await expect(card.getByText("Processed:", { exact: false })).toBeVisible();
  await card.getByRole("button", { name: "Disconnect", exact: true }).click();
  await confirm(page, "Disconnect integration?", "Disconnect");
  await expect(card.getByText("disconnected", { exact: true })).toBeVisible();
});

test("cancelled OAuth does not claim a connected integration", async ({
  page,
  context,
}) => {
  await apiLogin(context);
  await page.goto(
    "/integrations/callback?error=access_denied&state=discard-me",
  );
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "cancelled or denied",
  );
  expect(new URL(page.url()).search).toBe("");
  await expect(
    page.getByText("The backend confirmed the integration is connected."),
  ).toHaveCount(0);
});

for (const [capability, label, entityId, output] of [
  ["lead_score", "Lead", seed.lead, "score"],
  ["lead_summary", "Lead", seed.lead, "summary"],
  ["next_best_action", "Deal", seed.deal, "action"],
  ["reply_analysis", "Inbound message", seed.message, "classification"],
  ["campaign_draft", "Campaign", seed.campaign, "subject"],
  ["proposal_draft", "Deal", seed.deal, "proposal id"],
] as const) {
  test(`controlled AI ${capability} uses a real queued gateway operation and displays validated output`, async ({
    page,
    context,
  }) => {
    const session = await apiLogin(context);
    await page.goto("/ai-agents");
    await page
      .getByRole("combobox", { name: "Capability", exact: true })
      .selectOption(capability);
    if (capability === "reply_analysis")
      await page
        .getByRole("combobox", { name: "Conversation", exact: true })
        .selectOption(seed.conversation);
    await page
      .getByRole("combobox", { name: label, exact: true })
      .selectOption(entityId);
    const response = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/crm/operations/ai/requests") &&
        r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Queue AI request" }).click();
    const submitted = await response;
    expect(submitted.status()).toBe(202);
    const job = (await submitted.json()).id as string;
    await expect
      .poll(
        async () =>
          (
            await bodyOf<{ status: string }>(
              page,
              session,
              "/operations/jobs/" + job,
            )
          ).status,
        { timeout: 30000 },
      )
      .toBe("completed");
    await expect(
      page.getByText("Operation: completed", { exact: true }),
    ).toBeVisible();
    await expect(
      page.locator("dt").filter({ hasText: new RegExp("^" + output + "$") }),
    ).toBeVisible();
  });
}

test("failed workflow exposes its durable job and bounded retry preserves the failure record", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  const name = "Failing workflow " + randomUUID();
  let workflowId = "";
  try {
    await page.goto("/automations");
    await page.getByRole("button", { name: "New workflow" }).click();
    let dialog = page.getByRole("dialog", {
      name: "Create workflow",
      exact: true,
    });
    await dialog.getByLabel("Workflow name").fill(name);
    await dialog
      .getByLabel("title (required)", { exact: true })
      .fill("Must not create without a valid customer");
    await dialog.getByLabel("lead id", { exact: true }).fill(randomUUID());
    const created = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/crm/operations/workflows") &&
        response.request().method() === "POST",
    );
    await dialog
      .getByRole("button", { name: "Save disabled workflow" })
      .click();
    workflowId = (await (await created).json()).id;
    dialog = page.getByRole("dialog", {
      name: "Workflow details",
      exact: true,
    });
    await dialog
      .getByRole("button", { name: "Enable workflow", exact: true })
      .click();
    await expect(
      dialog.getByRole("button", { name: "Disable workflow", exact: true }),
    ).toBeVisible();
    await page.goto("/leads");
    await page.getByRole("button", { name: "New Lead", exact: true }).click();
    const leadDialog = page.getByRole("dialog", {
      name: "New lead",
      exact: true,
    });
    await leadDialog
      .getByLabel("Lead title", { exact: true })
      .fill("Failure trigger " + randomUUID());
    await leadDialog
      .getByRole("button", { name: "Create lead", exact: true })
      .click();
    await expect
      .poll(
        async () =>
          (
            await bodyOf<{ items: { status: string }[] }>(
              page,
              session,
              `/operations/workflows/${workflowId}/executions`,
            )
          ).items.some((log) => log.status === "failed"),
        { timeout: 30000 },
      )
      .toBe(true);
    const executions = await bodyOf<{
      items: { id: string; status: string; job_id: string }[];
    }>(page, session, `/operations/workflows/${workflowId}/executions`);
    const execution = executions.items.find((log) => log.status === "failed")!;
    expect(execution.job_id).toMatch(/^[a-f\d-]{36}$/);
    await page.goto("/automations");
    await page
      .locator("article")
      .filter({ has: page.getByRole("heading", { name, exact: true }) })
      .getByRole("button")
      .click();
    dialog = page.getByRole("dialog", {
      name: "Workflow details",
      exact: true,
    });
    await expect(
      dialog.getByText("Operation: failed", { exact: true }),
    ).toBeVisible();
    await dialog
      .getByRole("button", { name: "Retry operation", exact: true })
      .click();
    await expect
      .poll(
        async () => {
          const job = await bodyOf<{ attempts: number; status: string }>(
            page,
            session,
            `/operations/jobs/${execution.job_id}`,
          );
          return [job.attempts, job.status];
        },
        { timeout: 30000 },
      )
      .toEqual([2, "failed"]);
    const retained = await bodyOf<{ items: { id: string }[] }>(
      page,
      session,
      `/operations/workflows/${workflowId}/executions`,
    );
    expect(retained.items.some((log) => log.id === execution.id)).toBe(true);
  } finally {
    if (workflowId) {
      const stopped = await context.request.patch(
        `/api/crm/operations/workflows/${workflowId}/enabled`,
        { headers: crmHeaders(session), data: { enabled: false } },
      );
      expect(stopped.ok()).toBe(true);
    }
  }
});

test("draft campaign sequence, metadata edit and confirmed deletion persist", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  const name = "Sequence " + randomUUID();
  const id = await createCampaign(page, name);
  const dialog = page.getByRole("dialog", {
    name: "Campaign details",
    exact: true,
  });
  await dialog
    .getByRole("button", { name: "Configure audience and messages" })
    .click();
  await dialog
    .getByRole("combobox", { name: "Connected email integration", exact: true })
    .selectOption(seed.integration);
  await dialog
    .getByRole("checkbox", {
      name: new RegExp(seed.contactEmail.replaceAll(".", "\\.")),
    })
    .check();
  await dialog.getByLabel("First message subject").fill("First step");
  await dialog.getByLabel("First message body").fill("Initial message");
  await dialog.getByRole("button", { name: "Add follow-up step" }).click();
  const followup = dialog.getByRole("group", {
    name: "Follow-up 1",
    exact: true,
  });
  await followup.getByLabel("Subject", { exact: true }).fill("Second step");
  await followup.getByLabel("Body", { exact: true }).fill("Follow-up message");
  await followup.getByLabel("Hours after previous step").fill("48");
  await dialog.getByRole("button", { name: "Save delivery plan" }).click();
  await expect(
    dialog
      .getByRole("status")
      .filter({ hasText: "Audience and message plan saved" }),
  ).toBeVisible();
  const planned = await bodyOf<{
    type: string;
    templates: { subject: string }[];
    sequences: { delay_days: number; delay_hours: number }[];
  }>(page, session, "/campaigns/" + id);
  expect(planned.type).toBe("sequence");
  expect(planned.templates).toHaveLength(2);
  expect(
    planned.sequences.some(
      (step) => step.delay_days === 2 && step.delay_hours === 0,
    ),
  ).toBe(true);
  await dialog
    .getByRole("button", { name: "Edit name and description" })
    .click();
  await dialog.getByLabel("Campaign name").fill(name + " revised");
  await dialog
    .getByLabel("Description", { exact: true })
    .fill("Saved metadata from the UI");
  await dialog.getByRole("button", { name: "Save campaign details" }).click();
  await expect
    .poll(
      async () =>
        (await bodyOf<{ name: string }>(page, session, "/campaigns/" + id))
          .name,
    )
    .toBe(name + " revised");
  await dialog
    .getByRole("button", { name: "Delete draft", exact: true })
    .click();
  await confirm(page, "Delete draft campaign?", "Delete draft");
  await expect(dialog).not.toBeVisible();
  expect(
    (
      await context.request.get("/api/crm/campaigns/" + id, {
        headers: crmHeaders(session),
      })
    ).status(),
  ).toBe(404);
});

test("reviewed AI hook approval retains and follows the distinct child AI request", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  const title = "Human approved lead " + randomUUID();
  await page.goto("/leads");
  await page.getByRole("button", { name: "New Lead", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "New lead", exact: true });
  await dialog.getByLabel("Lead title", { exact: true }).fill(title);
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/crm/leads") &&
      response.request().method() === "POST",
  );
  await dialog
    .getByRole("button", { name: "Create lead", exact: true })
    .click();
  const leadId = (await (await created).json()).id as string;
  type Hook = {
    id: string;
    status: string;
    result: {
      suggestion?: { capability: string; entity_id: string };
      job_id?: string;
    };
  };
  await expect
    .poll(
      async () =>
        (
          await bodyOf<{ items: Hook[] }>(
            page,
            session,
            "/operations/jobs?kind=ai_hook&state=awaiting_approval&limit=100",
          )
        ).items.some((item) => item.result.suggestion?.entity_id === leadId),
      { timeout: 30000 },
    )
    .toBe(true);
  const hooks = await bodyOf<{ items: Hook[] }>(
    page,
    session,
    "/operations/jobs?kind=ai_hook&state=awaiting_approval&limit=100",
  );
  const hook = hooks.items.find(
    (item) => item.result.suggestion?.entity_id === leadId,
  )!;
  expect(hook.result.suggestion?.capability).toBe("lead_score");
  await page.goto("/ai-agents");
  await page.getByRole("button", { name: "Review event suggestions" }).click();
  const suggestion = page
    .locator('div[aria-live="polite"]')
    .filter({ hasText: leadId });
  await expect(suggestion).toContainText("Suggestion: awaiting approval");
  await suggestion.getByRole("button", { name: "Review and approve" }).click();
  const approval = page.getByRole("dialog", {
    name: "Approve AI request",
    exact: true,
  });
  await expect(approval).toContainText(leadId);
  const accepted = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/crm/operations/jobs/${hook.id}/approve`) &&
      response.request().method() === "POST",
  );
  await approval
    .getByRole("button", { name: "Approve AI request", exact: true })
    .click();
  const response = await accepted;
  expect(response.status()).toBe(202);
  const child = (await response.json()) as { id: string; kind: string };
  expect(child.id).not.toBe(hook.id);
  expect(child.kind).toBe("ai");
  const approved = page.getByRole("region", {
    name: "Approved AI requests",
    exact: true,
  });
  await expect(approved).toBeVisible();
  await expect(
    approved.getByText("Operation: completed", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  const parent = await bodyOf<Hook>(
    page,
    session,
    `/operations/jobs/${hook.id}`,
  );
  expect(parent.status).toBe("completed");
  expect(parent.result.job_id).toBe(child.id);
  await page.reload();
  await expect(
    page.getByText(`Provenance: backend AI operation ${child.id}`, {
      exact: true,
    }),
  ).toBeVisible();
});

test("AI provider failure stays a failed durable job without synthetic results", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  const created = await context.request.post("/api/crm/leads", {
    headers: crmHeaders(session),
    data: {
      title: "[ai-provider-failure] " + randomUUID(),
      source: "manual",
      status: "new",
    },
  });
  expect(created.status()).toBe(201);
  const leadId = (await created.json()).id as string;
  await page.goto("/ai-agents");
  await page
    .getByRole("combobox", { name: "Capability", exact: true })
    .selectOption("lead_score");
  await page
    .getByRole("combobox", { name: "Lead", exact: true })
    .selectOption(leadId);
  const response = page.waitForResponse(
    (item) =>
      item.url().endsWith("/api/crm/operations/ai/requests") &&
      item.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Queue AI request" }).click();
  const result = await response;
  expect(result.status()).toBe(202);
  const id = (await result.json()).id as string;
  await expect
    .poll(
      async () =>
        (
          await bodyOf<{ status: string }>(
            page,
            session,
            `/operations/jobs/${id}`,
          )
        ).status,
      { timeout: 30000 },
    )
    .toBe("failed");
  await expect(
    page.getByText("Operation: failed", { exact: true }),
  ).toBeVisible();
  const failed = await bodyOf<{
    result: Record<string, unknown>;
    error_code: string;
  }>(page, session, `/operations/jobs/${id}`);
  expect(failed.error_code).toBeTruthy();
  expect(failed.result.score).toBeUndefined();
  await expect(
    page.getByRole("button", { name: "Retry operation" }),
  ).toHaveCount(0);
});

function setAIQuota(state: { enabled: boolean; limit: number | null }): {
  enabled: boolean;
  limit: number | null;
} {
  const output = execFileSync(
    process.env.CP4_PYTHON ?? "python",
    [
      path.resolve(__dirname, "../../../scripts/checkpoint4_quota_fixture.py"),
      JSON.stringify(state),
    ],
    {
      cwd: path.resolve(__dirname, "../../.."),
      env: { ...process.env, APP_ENVIRONMENT: "testing" },
      encoding: "utf8",
      timeout: 30000,
    },
  );
  return JSON.parse(output.trim()) as {
    enabled: boolean;
    limit: number | null;
  };
}

test("exhausted real AI quota returns visible 403 and creates no new job", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  const previous = setAIQuota({ enabled: true, limit: 0 });
  try {
    const before = await bodyOf<{ total: number }>(
      page,
      session,
      "/operations/jobs?kind=ai&limit=1",
    );
    await page.goto("/ai-agents");
    await page
      .getByRole("combobox", { name: "Capability", exact: true })
      .selectOption("lead_score");
    await page
      .getByRole("combobox", { name: "Lead", exact: true })
      .selectOption(seed.lead);
    const rejected = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/crm/operations/ai/requests") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Queue AI request" }).click();
    expect((await rejected).status()).toBe(403);
    await expect(
      page
        .getByRole("alert")
        .filter({ hasText: /Feature limit exceeded|quota|limit/i }),
    ).toBeVisible();
    const after = await bodyOf<{ total: number }>(
      page,
      session,
      "/operations/jobs?kind=ai&limit=1",
    );
    expect(after.total).toBe(before.total);
    await expect(
      page.getByRole("heading", { name: "Latest request", exact: true }),
    ).toHaveCount(0);
  } finally {
    setAIQuota(previous);
  }
});

for (const outcome of [
  { marker: "provider-failure", status: "failed", field: "failed" },
  { marker: "provider-unknown", status: "unknown", field: "unknown" },
] as const) {
  test(`campaign ${outcome.status} provider outcome is visible and never displayed as delivered`, async ({
    page,
    context,
  }) => {
    const session = await apiLogin(context);
    const id = await createCampaign(
      page,
      `${outcome.status} campaign ${randomUUID()}`,
    );
    const dialog = page.getByRole("dialog", {
      name: "Campaign details",
      exact: true,
    });
    await dialog
      .getByRole("button", { name: "Configure audience and messages" })
      .click();
    await dialog
      .getByRole("combobox", {
        name: "Connected email integration",
        exact: true,
      })
      .selectOption(seed.integration);
    await dialog
      .getByRole("checkbox", {
        name: new RegExp(seed.contactEmail.replaceAll(".", "\\.")),
      })
      .check();
    await dialog
      .getByLabel("First message subject")
      .fill(`[${outcome.marker}] controlled delivery test`);
    await dialog
      .getByLabel("First message body")
      .fill(
        "Only the isolated external provider adapter receives this request.",
      );
    await dialog.getByRole("button", { name: "Save delivery plan" }).click();
    await expect(
      dialog
        .getByRole("status")
        .filter({ hasText: "Audience and message plan saved" }),
    ).toBeVisible();
    await dialog
      .getByRole("button", { name: "Launch campaign", exact: true })
      .click();
    await confirm(page, "Launch campaign?", "Launch campaign");
    await expect
      .poll(
        async () =>
          (
            await bodyOf<Record<string, number>>(
              page,
              session,
              `/operations/campaigns/${id}/statistics`,
            )
          )[outcome.field],
        { timeout: 30000 },
      )
      .toBe(1);
    await dialog
      .getByRole("button", { name: "Refresh status", exact: true })
      .click();
    const stats = await bodyOf<{
      sent: number;
      unknown: number;
      failed: number;
    }>(page, session, `/operations/campaigns/${id}/statistics`);
    expect(stats.sent).toBe(0);
    if (outcome.status === "unknown") {
      await expect(
        dialog.getByText(
          /Delivery status pending verification for 1 operation/,
        ),
      ).toBeVisible();
      await expect(
        dialog.getByRole("button", { name: /resume|launch/i }),
      ).toHaveCount(0);
      await dialog
        .getByRole("button", { name: "Cancel campaign", exact: true })
        .click();
      await confirm(page, "Cancel campaign?", "Cancel campaign");
    } else {
      const recipients = await bodyOf<{ items: { status: string }[] }>(
        page,
        session,
        `/campaigns/${id}/recipients`,
      );
      expect(recipients.items.every((item) => item.status === "failed")).toBe(
        true,
      );
    }
  });
}
