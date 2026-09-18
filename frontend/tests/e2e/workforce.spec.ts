import { test, expect, type Page, type BrowserContext } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { randomUUID } from "node:crypto";
import { apiLogin, crmHeaders, fixture } from "./helpers";
import type { AgentExecution, Approval } from "../../src/types/workforce";
import type { Session } from "../../src/auth/types";
import type { Page as ApiPage } from "../../src/types/operations";

const seed = fixture.records.tenantA;
async function execution(
  context: BrowserContext,
  session: Session,
  id: string,
) {
  const response = await context.request.get(
    `/api/crm/workforce/executions/${id}`,
    { headers: crmHeaders(session) },
  );
  expect(response.status()).toBe(200);
  return (await response.json()) as AgentExecution;
}
async function requestThroughUI(
  page: Page,
  objective: string,
  supervisor = false,
) {
  await page.goto(supervisor ? "/supervisor" : "/ai-workforce");
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: supervisor ? "Supervisor" : "AI Workforce",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: supervisor ? "New objective" : "New agent task",
      exact: true,
    })
    .click();
  const dialog = page.getByRole("dialog", {
    name: supervisor ? "New objective" : "New agent task",
    exact: true,
  });
  await dialog.getByLabel("Objective", { exact: true }).fill(objective);
  await dialog
    .getByRole("combobox", { name: "Related record", exact: true })
    .selectOption(seed.lead);
  const request = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/crm/workforce/executions") &&
      response.request().method() === "POST",
  );
  await dialog
    .getByRole("button", {
      name: supervisor ? "Queue objective" : "Queue agent task",
      exact: true,
    })
    .click();
  const response = await request;
  expect(response.status()).toBe(202);
  expect(response.request().headers()["idempotency-key"]).toMatch(
    /^[a-f\d-]{36}$/,
  );
  return (await response.json()) as AgentExecution;
}

test("workforce queues a real execution and shows its completed result in Customer 360", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  const objective = `Review the linked lead ${randomUUID()}`;
  const queued = await requestThroughUI(page, objective);
  await expect
    .poll(async () => (await execution(context, session, queued.id)).state, {
      timeout: 45000,
    })
    .toBe("completed");
  const dialog = page.getByRole("dialog", {
    name: "Execution details",
    exact: true,
  });
  await expect(dialog.getByRole("status")).toContainText("completed");
  await expect(
    dialog.getByRole("heading", { name: "Recorded result" }),
  ).toBeVisible();
  await page.goto(`/customers/leads/${seed.lead}`);
  await expect(
    page.getByRole("heading", { name: "Customer AI activity", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: new RegExp(objective) }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Create agent task", exact: true })
    .click();
  const newTask = page.getByRole("dialog", {
    name: "New agent task",
    exact: true,
  });
  await expect(
    newTask.getByRole("combobox", { name: "Related record", exact: true }),
  ).toHaveValue(seed.lead);
});

test("supervisor displays actual assigned children and consolidated results", async ({
  page,
  context,
}) => {
  const session = await apiLogin(context);
  const queued = await requestThroughUI(
    page,
    `Prepare a bounded customer review ${randomUUID()}`,
    true,
  );
  await expect
    .poll(async () => (await execution(context, session, queued.id)).state, {
      timeout: 45000,
    })
    .toBe("completed");
  const completed = await execution(context, session, queued.id);
  expect(completed.children?.length).toBeGreaterThan(0);
  expect(
    completed.children?.every((child) => child.state === "completed"),
  ).toBe(true);
  await expect(
    page.getByRole("heading", { name: "Assigned work", exact: true }),
  ).toBeVisible();
});

test("memory requires independent exact-action approval and can be deleted after execution", async ({
  page,
  context,
  browser,
}) => {
  const requester = await apiLogin(context);
  const memoryKey = `Customer preference ${randomUUID()}`;
  await page.goto("/ai-workforce");
  await page
    .getByRole("button", { name: "Propose memory", exact: true })
    .click();
  const proposal = page.getByRole("dialog", {
    name: "Propose long-term memory",
    exact: true,
  });
  await proposal.getByLabel("Memory key", { exact: true }).fill(memoryKey);
  await proposal
    .getByLabel("Approved context to retain", { exact: true })
    .fill("Only retain a reviewed preference for 7 days.");
  await proposal.getByLabel("Retention days", { exact: true }).fill("7");
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/crm/workforce/memory") &&
      response.request().method() === "POST",
  );
  await proposal
    .getByRole("button", { name: "Request memory approval", exact: true })
    .click();
  const response = await responsePromise;
  expect(response.status()).toBe(202);
  const approval = (await response.json()) as Approval;
  await page.goto("/approvals");
  const ownCard = page
    .locator("article")
    .filter({ hasText: "remember" })
    .first();
  await ownCard
    .getByRole("button", { name: "Review action", exact: true })
    .click();
  await expect(
    page.getByText(
      "Another authorized reviewer must decide this request. You cannot approve your own action.",
      { exact: true },
    ),
  ).toBeVisible();
  expect(
    (
      await context.request.post(
        `/api/crm/workforce/approvals/${approval.id}/decision`,
        {
          headers: crmHeaders(requester),
          data: { decision: "approved", action_hash: approval.action_hash },
        },
      )
    ).status(),
  ).toBe(403);
  const reviewerContext = await browser.newContext({ baseURL: fixture.origin });
  try {
    const reviewer = await apiLogin(reviewerContext, "admin");
    expect(
      (
        await reviewerContext.request.post(
          `/api/crm/workforce/approvals/${approval.id}/decision`,
          {
            headers: crmHeaders(reviewer),
            data: { decision: "approved", action_hash: "0".repeat(64) },
          },
        )
      ).status(),
    ).toBe(409);
    const reviewerPage = await reviewerContext.newPage();
    await reviewerPage.goto("/approvals");
    await reviewerPage
      .locator("article")
      .filter({ hasText: "remember" })
      .first()
      .getByRole("button", { name: "Review action", exact: true })
      .click();
    const review = reviewerPage.getByRole("dialog", {
      name: "Review exact action",
      exact: true,
    });
    await expect(review).toContainText(memoryKey);
    await review
      .getByRole("button", { name: "Approve exact action", exact: true })
      .click();
    await reviewerPage
      .getByRole("dialog", { name: "Approve this exact action?", exact: true })
      .getByRole("button", { name: "Approve exact action", exact: true })
      .click();
    await expect
      .poll(
        async () => {
          const response = await reviewerContext.request.get(
            "/api/crm/workforce/approvals?limit=100",
            { headers: crmHeaders(reviewer) },
          );
          expect(response.status()).toBe(200);
          return ((await response.json()) as ApiPage<Approval>).items.find(
            (item) => item.id === approval.id,
          )?.status;
        },
        { timeout: 45000 },
      )
      .toBe("executed");
    await expect(review.getByRole("status")).toContainText("executed");
  } finally {
    await reviewerContext.close();
  }
  await page.goto("/ai-workforce");
  const memory = page
    .locator("li")
    .filter({ has: page.getByText(memoryKey, { exact: true }) });
  await expect(memory).toContainText("approved");
  await memory
    .getByRole("button", { name: "Delete memory", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Delete agent memory?", exact: true })
    .getByRole("button", { name: "Delete memory", exact: true })
    .click();
  await expect(page.getByText(memoryKey, { exact: true })).toHaveCount(0);
});

test("workforce enforces tenant boundaries and rejects authority overrides", async ({
  context,
}) => {
  let session = await apiLogin(context);
  const invalid = await context.request.post("/api/crm/workforce/executions", {
    headers: { ...crmHeaders(session), "Idempotency-Key": randomUUID() },
    data: {
      agent_name: "research",
      objective: "Review one lead",
      context: { tenant_id: fixture.tenantB },
      tools: [],
    },
  });
  expect(invalid.status()).toBe(422);
  const create = await context.request.post("/api/crm/workforce/executions", {
    headers: { ...crmHeaders(session), "Idempotency-Key": randomUUID() },
    data: {
      agent_name: "research",
      objective: "Review tenant A lead",
      context: { entity_type: "lead", entity_id: seed.lead },
      tools: [],
    },
  });
  expect(create.status()).toBe(202);
  const created = (await create.json()) as AgentExecution;
  const switchTenant = await context.request.post("/api/session/tenant", {
    headers: crmHeaders(session),
    data: { tenant_id: fixture.tenantB },
  });
  expect(switchTenant.status()).toBe(200);
  session = (await switchTenant.json()) as Session;
  expect(
    (
      await context.request.get(`/api/crm/workforce/executions/${created.id}`, {
        headers: crmHeaders(session),
      })
    ).status(),
  ).toBe(404);
});

test("AI drafts and sends only after independent approvals, then exposes actual provider state", async ({
  page,
  context,
  browser,
}) => {
  test.setTimeout(150000);
  const requester = await apiLogin(context);
  const message = `Reviewed follow-up ${randomUUID()}`;
  await page.goto(
    `/ai-workforce?entity_type=conversation&entity_id=${seed.conversation}`,
  );
  const task = page.getByRole("dialog", {
    name: "New agent task",
    exact: true,
  });
  await task.getByRole("combobox", { name: "Agent", exact: true }).selectOption("sales");
  await task
    .getByLabel("Objective", { exact: true })
    .fill(
      `[cp56-send-review] ${JSON.stringify({ recipient: seed.contactEmail, body: message })}`,
    );
  await task
    .getByRole("checkbox", { name: "draft email", exact: true })
    .check();
  await task.getByRole("checkbox", { name: "send email", exact: true }).check();
  const submitted = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/crm/workforce/executions") &&
      response.request().method() === "POST",
  );
  await task
    .getByRole("button", { name: "Queue agent task", exact: true })
    .click();
  const response = await submitted;
  expect(response.status()).toBe(202);
  const queued = (await response.json()) as AgentExecution;
  await expect
    .poll(async () => (await execution(context, requester, queued.id)).state, {
      timeout: 45000,
    })
    .toBe("completed");
  const completed = await execution(context, requester, queued.id);
  expect(completed.result?.approvals).toHaveLength(2);
  const reviewerContext = await browser.newContext({ baseURL: fixture.origin });
  try {
    const reviewer = await apiLogin(reviewerContext, "admin");
    const reviewerPage = await reviewerContext.newPage();
    for (const actionType of ["draft_email", "send_email"]) {
      await reviewerPage.goto("/approvals");
      await reviewerPage
        .locator("article")
        .filter({
          has: reviewerPage.getByRole("heading", {
            name: actionType.replaceAll("_", " "),
            exact: true,
          }),
        })
        .first()
        .getByRole("button", { name: "Review action", exact: true })
        .click();
      const review = reviewerPage.getByRole("dialog", {
        name: "Review exact action",
        exact: true,
      });
      await expect(review).toContainText(message);
      if (actionType === "send_email")
        await expect(review).toContainText(seed.contactEmail);
      const decision = reviewerPage.waitForResponse(
        (result) =>
          /\/workforce\/approvals\/[^/]+\/decision$/.test(result.url()) &&
          result.request().method() === "POST",
      );
      await review
        .getByRole("button", { name: "Approve exact action", exact: true })
        .click();
      await reviewerPage
        .getByRole("dialog", {
          name: "Approve this exact action?",
          exact: true,
        })
        .getByRole("button", { name: "Approve exact action", exact: true })
        .click();
      const result = await decision;
      expect(result.status(), await result.text()).toBe(200);
      const approved = (await result.json()) as Approval;
      expect(approved.status).toBe("approved");
      await expect
        .poll(
          async () => {
            const response = await reviewerContext.request.get(
              "/api/crm/workforce/approvals?limit=100",
              { headers: crmHeaders(reviewer) },
            );
            expect(response.status()).toBe(200);
            return ((await response.json()) as ApiPage<Approval>).items.find(
              (item) => item.id === approved.id,
            )?.status;
          },
          { timeout: 45000 },
        )
        .toBe("executed");
    }
  } finally {
    await reviewerContext.close();
  }
  await page.goto(`/conversations?conversation=${seed.conversation}`);
  const sent = page
    .locator("article")
    .filter({ has: page.getByText(message, { exact: true }) })
    .filter({ hasText: "fixture-" });
  await expect(sent).toContainText("sent");
  await expect(sent).not.toContainText("delivered");
  await page.goto(`/customers/leads/${seed.lead}`);
  await expect(page.getByText(message, { exact: true }).first()).toBeVisible();
});

for (const size of [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
]) {
  test(`workforce routes are loaded, accessible and responsive at ${size.width}px`, async ({
    page,
    context,
  }, info) => {
    test.setTimeout(120000);
    await apiLogin(context);
    await page.setViewportSize(size);
    for (const [route, heading, endpoint] of [
      ["/ai-workforce", "AI Workforce", "/workforce/agents"],
      ["/supervisor", "Supervisor", "/workforce/executions"],
      ["/approvals", "Approval Center", "/workforce/approvals"],
    ]) {
      const data = page.waitForResponse(
        (response) =>
          response.url().includes("/api/crm" + endpoint) &&
          response.request().method() === "GET",
      );
      await page.goto(route);
      expect((await data).status()).toBe(200);
      await expect(
        page.getByRole("heading", { level: 1, name: heading, exact: true }),
      ).toBeVisible();
      await expect(page.locator(".session-state")).toHaveCount(0);
      await expect(
        page.getByText("Loading workspace data…", { exact: true }),
      ).toHaveCount(0);
      const audit = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(
        audit.violations.filter((violation) =>
          ["serious", "critical"].includes(violation.impact || ""),
        ),
      ).toEqual([]);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth + 1,
        ),
      ).toBe(false);
      await page.screenshot({
        path: info.outputPath(`workforce-${route.slice(1)}-${size.width}.png`),
        fullPage: true,
        animations: "disabled",
      });
    }
  });
}
