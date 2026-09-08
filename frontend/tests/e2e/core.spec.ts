import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { fixture, loginUI, backend, saved } from "./coreFixtures";
test.setTimeout(120000);

test("CRM creates related company, contact and lead, updates a lead and persists Customer360 work", async ({
  page,
  request,
}) => {
  const suffix = randomUUID().slice(0, 8);
  await loginUI(page);
  const api = await backend(request);
  await page.goto("/companies");
  await page.getByRole("button", { name: "New Company", exact: true }).click();
  let dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Company name", { exact: true })
    .fill(`CRM Account ${suffix}`);
  await dialog.getByLabel("Industry", { exact: true }).fill("Software");
  const company = await saved(page, "/companies", () =>
    dialog.getByRole("button", { name: "Create company", exact: true }).click(),
  );
  await expect(dialog).not.toBeVisible();
  expect(company.id).toMatch(/^[0-9a-f-]{36}$/);
  await page.goto("/contacts");
  await page.getByRole("button", { name: "New Contact", exact: true }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("First name", { exact: true }).fill(`CRM ${suffix}`);
  await dialog.getByLabel("Last name", { exact: true }).fill("Contact");
  await dialog
    .getByLabel("Email", { exact: true })
    .fill(`crm-${suffix}@example.com`);
  await expect(
    dialog
      .getByRole("combobox", { name: "Company", exact: true })
      .locator(`option[value="${company.id}"]`),
  ).toBeAttached();
  await dialog
    .getByRole("combobox", { name: "Company", exact: true })
    .selectOption(company.id);
  const contact = await saved(page, "/contacts", () =>
    dialog.getByRole("button", { name: "Create contact", exact: true }).click(),
  );
  await expect(dialog).not.toBeVisible();
  expect(contact.company_id).toBe(company.id);
  await page.goto("/leads");
  await page.getByRole("button", { name: "New Lead", exact: true }).click();
  dialog = page.getByRole("dialog");
  const title = `CRM Opportunity ${suffix}`;
  await dialog.getByLabel("Lead title", { exact: true }).fill(title);
  await dialog
    .getByRole("combobox", { name: "Company", exact: true })
    .selectOption(company.id);
  await dialog
    .getByRole("combobox", { name: "Contact", exact: true })
    .selectOption(contact.id);
  await dialog
    .getByRole("combobox", { name: "Source", exact: true })
    .selectOption("referral");
  const lead = await saved(page, "/leads", () =>
    dialog.getByRole("button", { name: "Create lead", exact: true }).click(),
  );
  await expect(dialog).not.toBeVisible();
  expect(lead.owner_id).toBe(fixture.users.owner.id);
  expect(lead.contact_id).toBe(contact.id);
  await page.getByRole("button", { name: title, exact: true }).click();
  const drawer = page.getByRole("dialog", { name: title, exact: true });
  await expect(
    drawer.getByRole("link", {
      name: `crm-${suffix}@example.com`,
      exact: true,
    }),
  ).toBeVisible();
  await drawer.getByRole("button", { name: "Edit lead", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "Edit lead", exact: true });
  await dialog
    .getByLabel("Description", { exact: true })
    .fill("Verified customer need from the discovery call.");
  await saved(
    page,
    `/leads/${lead.id}`,
    () =>
      dialog.getByRole("button", { name: "Save changes", exact: true }).click(),
    "PATCH",
  );
  await expect(dialog).not.toBeVisible();
  await drawer
    .getByRole("combobox", { name: "Lead status", exact: true })
    .selectOption("qualified");
  await expect
    .poll(async () => {
      const response = await api.get(`/leads/${lead.id}`);
      return (await response.json()).status;
    })
    .toBe("qualified");
  await drawer
    .getByRole("button", { name: "Request AI score", exact: true })
    .click();
  await expect(drawer.getByText(/Operation: completed/)).toBeVisible({
    timeout: 45000,
  });
  await expect
    .poll(async () => {
      const response = await api.get(`/leads/${lead.id}`);
      return (await response.json()).ai_score;
    })
    .toBeGreaterThanOrEqual(0);
  await drawer
    .getByRole("link", { name: "Customer 360 & timeline", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { level: 1, name: title }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /Contacts \(1\)/ }),
  ).toBeVisible();
  await page
    .getByLabel("Note", { exact: true })
    .fill(`Discovery note ${suffix}`);
  await saved(page, "/notes", () =>
    page.getByRole("button", { name: "Save note", exact: true }).click(),
  );
  await expect(
    page.getByText(`Discovery note ${suffix}`, { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Meeting subject", { exact: true })
    .fill(`Discovery meeting ${suffix}`);
  await saved(page, "/operations/activities", () =>
    page.getByRole("button", { name: "Log activity", exact: true }).click(),
  );
  await expect(
    page.getByText(`Discovery meeting ${suffix}`, { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Create Task", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "Create task", exact: true });
  await dialog
    .getByLabel("Task title", { exact: true })
    .fill(`Follow up ${suffix}`);
  await dialog
    .getByRole("combobox", { name: "Priority", exact: true })
    .selectOption("high");
  await dialog
    .getByLabel("Due date and time", { exact: true })
    .fill("2027-01-05T10:30");
  const task = await saved(page, "/tasks", () =>
    dialog.getByRole("button", { name: "Create task", exact: true }).click(),
  );
  await expect(dialog).not.toBeVisible();
  expect(task.lead_id).toBe(lead.id);
  expect(task.priority).toBe("high");
  await expect
    .poll(
      async () => {
        const response = await api.get(
          `/operations/customers/leads/${lead.id}`,
        );
        return (await response.json()).timeline.map(
          (row: { type: string }) => row.type,
        );
      },
      { timeout: 30000 },
    )
    .toEqual(
      expect.arrayContaining([
        "lead.created",
        "note.created",
        "activity.created",
        "task.created",
      ]),
    );
  await page.reload();
  await expect(
    page.getByText(`Discovery note ${suffix}`, { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Note created", { exact: true })).toBeVisible();
  await page.goto(`/tasks?id=${task.id}`);
  dialog = page.getByRole("dialog", { name: "Edit task", exact: true });
  await expect(dialog.getByLabel("Task title", { exact: true })).toHaveValue(
    `Follow up ${suffix}`,
  );
  await dialog
    .getByRole("combobox", { name: "Status", exact: true })
    .selectOption("completed");
  await saved(
    page,
    `/tasks/${task.id}`,
    () =>
      dialog.getByRole("button", { name: "Save changes", exact: true }).click(),
    "PATCH",
  );
  const persisted = await (await api.get(`/tasks/${task.id}`)).json();
  expect(persisted.status).toBe("completed");
  expect(persisted.completed_at).toBeTruthy();
});

test("contact opt-outs and confirmed deletion persist; invalid input does not create records", async ({
  page,
  request,
}) => {
  await loginUI(page);
  const api = await backend(request);
  const suffix = randomUUID().slice(0, 8);
  await page.goto("/contacts");
  await page.getByRole("button", { name: "New Contact", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("First name", { exact: true }).fill("Policy");
  await dialog.getByLabel("Last name", { exact: true }).fill(suffix);
  await dialog.getByLabel("Email", { exact: true }).fill("not-an-email");
  await dialog
    .getByRole("button", { name: "Create contact", exact: true })
    .click();
  await expect(dialog).toBeVisible();
  expect(
    await dialog
      .getByLabel("Email", { exact: true })
      .evaluate((node: HTMLInputElement) => node.validity.valid),
  ).toBe(false);
  await dialog
    .getByLabel("Email", { exact: true })
    .fill(`policy-${suffix}@example.com`);
  await dialog.getByLabel("Email opted out", { exact: true }).check();
  await dialog.getByLabel("Do not contact", { exact: true }).check();
  const contact = await saved(page, "/contacts", () =>
    dialog.getByRole("button", { name: "Create contact", exact: true }).click(),
  );
  await expect(dialog).not.toBeVisible();
  const persisted = await (await api.get(`/contacts/${contact.id}`)).json();
  expect(persisted.email_opted_out).toBe(true);
  expect(persisted.do_not_contact).toBe(true);
  await page
    .getByRole("button", { name: `Delete Policy ${suffix}`, exact: true })
    .click();
  const confirm = page.getByRole("dialog", {
    name: "Delete contact?",
    exact: true,
  });
  await expect(confirm).toBeVisible();
  await saved(
    page,
    `/contacts/${contact.id}`,
    () => confirm.getByRole("button", { name: "Delete", exact: true }).click(),
    "DELETE",
  );
  expect((await api.get(`/contacts/${contact.id}`)).status()).toBe(404);
  await page.goto("/tasks");
  await page.getByRole("button", { name: "New Task", exact: true }).click();
  await page
    .getByLabel("Task title", { exact: true })
    .fill("Unlinked task rejected");
  await page.getByRole("button", { name: "Create task", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "New task", exact: true }).getByRole("alert"),
  ).toContainText("Choose at least one");
});

test("deal creation, drag, keyboard movement and atomic stage reorder persist", async ({
  page,
  request,
}) => {
  await loginUI(page);
  const api = await backend(request);
  const rec = fixture.records.tenantA;
  const newLeadResponse = await api.post("/leads", {
    title: `Deal source ${randomUUID().slice(0, 8)}`,
    source: "manual",
    owner_id: fixture.users.owner.id,
  });
  expect(newLeadResponse.ok()).toBe(true);
  const newLead = await newLeadResponse.json();
  await page.goto("/pipeline");
  await page
    .getByRole("combobox", { name: "Pipeline", exact: true })
    .selectOption(rec.pipeline);
  await page.getByRole("button", { name: "New Deal", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "New deal", exact: true });
  const title = `Deal ${randomUUID().slice(0, 8)}`;
  await dialog.getByLabel("Deal title", { exact: true }).fill(title);
  await dialog
    .getByRole("combobox", { name: "Stage", exact: true })
    .selectOption(rec.stage);
  await dialog
    .getByLabel("Value (minor units, e.g. 10000 = 100.00)", { exact: true })
    .fill("12345");
  await dialog
    .getByLabel("Currency (three-letter code)", { exact: true })
    .fill("EUR");
  await dialog
    .getByRole("combobox", { name: "Lead", exact: true })
    .selectOption(newLead.id);
  const deal = await saved(page, "/deals", () =>
    dialog.getByRole("button", { name: "Create deal", exact: true }).click(),
  );
  await expect(dialog).not.toBeVisible();
  expect(deal.currency).toBe("EUR");
  expect(deal.value).toBe(12345);
  const card = page
    .getByRole("article")
    .filter({ has: page.getByRole("button", { name: title, exact: false }) });
  const qualified = page.getByRole("region", {
    name: "Qualified stage",
    exact: true,
  });
  await expect(card).toHaveAttribute("draggable", "true");
  await expect(
    card.getByRole("combobox", { name: `Stage for ${title}`, exact: true }),
  ).toBeEnabled();
  const moved = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      response.request().method() === "POST" &&
      url.pathname === `/api/crm/deals/${deal.id}/move` &&
      url.searchParams.get("stage_id") === rec.stage2
    );
  });
  // Start in card padding, away from nested inputs/links. Two actual pointer
  // moves over the destination reliably dispatch native dragover in Chromium.
  await card.hover({ position: { x: 8, y: 8 } });
  await page.mouse.down();
  try {
    await qualified.hover({ position: { x: 20, y: 120 } });
    await qualified.hover({ position: { x: 24, y: 124 } });
  } finally {
    await page.mouse.up();
  }
  const moveResponse = await moved;
  expect(moveResponse.status()).toBe(200);
  expect((await moveResponse.json()).stage_id).toBe(rec.stage2);
  await expect
    .poll(
      async () => (await (await api.get(`/deals/${deal.id}`)).json()).stage_id,
    )
    .toBe(rec.stage2);
  await page
    .getByRole("combobox", { name: `Stage for ${title}`, exact: true })
    .selectOption(rec.stage3);
  await expect
    .poll(
      async () => (await (await api.get(`/deals/${deal.id}`)).json()).stage_id,
    )
    .toBe(rec.stage3);
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: `Stage for ${title}`, exact: true }),
  ).toHaveValue(rec.stage3);
  const before = await (
    await api.get(`/deals/pipelines/${rec.pipeline}/stages`)
  ).json();
  await page
    .getByRole("button", { name: "Move Qualified left", exact: true })
    .click();
  await expect
    .poll(async () =>
      (
        await (await api.get(`/deals/pipelines/${rec.pipeline}/stages`)).json()
      ).map((s: { id: string }) => s.id),
    )
    .toEqual([
      before[1].id,
      before[0].id,
      ...before.slice(2).map((s: { id: string }) => s.id),
    ]);
  await page
    .getByRole("button", { name: "Move Qualified right", exact: true })
    .click();
  await expect
    .poll(async () =>
      (
        await (await api.get(`/deals/pipelines/${rec.pipeline}/stages`)).json()
      ).map((s: { id: string }) => s.id),
    )
    .toEqual(before.map((s: { id: string }) => s.id));
});

test("revoked backend permission rejects a stale pipeline move and rolls the board back", async ({
  page,
  request,
}) => {
  const owner = await backend(request);
  const rec = fixture.records.tenantA;
  const persisted = await (await owner.get(`/deals/${rec.deal}`)).json();
  await loginUI(page, "sales_manager");
  await page.goto("/pipeline");
  await page
    .getByRole("combobox", { name: "Pipeline", exact: true })
    .selectOption(rec.pipeline);
  const select = page.getByLabel("Stage for Alpha discovery deal", {
    exact: true,
  });
  await expect(select).toHaveValue(persisted.stage_id);
  const changed = await owner.patch(
    `/users/${fixture.users.sales_manager.id}/memberships`,
    { role: "viewer" },
  );
  try {
    expect(changed.ok()).toBe(true);
    const rejected = page.waitForResponse(
      (r) =>
        r.url().includes(`/deals/${rec.deal}/move`) &&
        r.request().method() === "POST",
    );
    await select.selectOption(
      persisted.stage_id === rec.stage2 ? rec.stage3 : rec.stage2,
    );
    expect((await rejected).status()).toBe(403);
    await expect(
      page.getByRole("alert").filter({ hasText: "last confirmed stage" }),
    ).toBeVisible();
    await expect(select).toHaveValue(persisted.stage_id);
    expect(
      (await (await owner.get(`/deals/${rec.deal}`)).json()).stage_id,
    ).toBe(persisted.stage_id);
  } finally {
    const restored = await owner.patch(
      `/users/${fixture.users.sales_manager.id}/memberships`,
      { role: "sales_manager" },
    );
    expect(restored.ok()).toBe(true);
  }
});

test("another browser context sees confirmed CRM changes after reload", async ({
  page,
  browser,
  request,
}) => {
  const api = await backend(request);
  const created = await api.post("/leads", {
    title: `Shared ${randomUUID().slice(0, 8)}`,
    source: "manual",
    owner_id: fixture.users.owner.id,
  });
  expect(created.ok()).toBe(true);
  const lead = await created.json();
  await loginUI(page);
  await page.goto("/leads");
  await page.getByRole("button", { name: lead.title, exact: true }).click();
  const other = await browser.newContext();
  try {
    const second = await other.newPage();
    await loginUI(second);
    await second.goto("/leads");
    await second.getByRole("button", { name: lead.title, exact: true }).click();
    await second
      .getByRole("dialog", { name: lead.title, exact: true })
      .getByRole("combobox", { name: "Lead status", exact: true })
      .selectOption("nurturing");
    await expect
      .poll(
        async () => (await (await api.get(`/leads/${lead.id}`)).json()).status,
      )
      .toBe("nurturing");
    await page.reload();
    await page.getByRole("button", { name: lead.title, exact: true }).click();
    await expect(
      page
        .getByRole("dialog", { name: lead.title, exact: true })
        .getByRole("combobox", { name: "Lead status", exact: true }),
    ).toHaveValue("nurturing");
  } finally {
    await other.close();
  }
});
