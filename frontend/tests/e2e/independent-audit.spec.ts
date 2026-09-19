import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { backend, loginUI, saved } from "./coreFixtures";

test("marketing edits an unassigned lead without changing its owner or gaining delete controls", async ({
  page,
  request,
}) => {
  const api = await backend(request);
  const title = `Independent audit ${randomUUID().slice(0, 8)}`;
  const created = await api.post("/leads", { title, owner_id: null });
  expect(created.status()).toBe(201);
  const lead = await created.json();
  try {
    await loginUI(page, "marketing");
    await page.goto("/leads");
    await page.getByLabel("Search leads", { exact: true }).fill(title);
    await page.getByRole("button", { name: title, exact: true }).click();
    await page
      .getByRole("dialog", { name: title, exact: true })
      .getByRole("button", { name: "Edit lead", exact: true })
      .click();
    const editor = page.getByRole("dialog", { name: "Edit lead", exact: true });
    await expect(
      editor.getByRole("combobox", { name: "Owner", exact: true }),
    ).toHaveCount(0);
    await editor
      .getByLabel("Description", { exact: true })
      .fill("Audited edit by marketing");
    await saved(
      page,
      `/leads/${lead.id}`,
      () =>
        editor
          .getByRole("button", { name: "Save changes", exact: true })
          .click(),
      "PATCH",
    );
    const persisted = await api.get(`/leads/${lead.id}`);
    expect((await persisted.json()).owner_id).toBeNull();
    await page.goto("/campaigns");
    const campaign = await api.post("/campaigns", {
      name: title,
      sender_name: "Audit",
      sender_email: "audit@example.com",
    });
    expect(campaign.status()).toBe(201);
    const record = await campaign.json();
    try {
      await page.reload();
      await page
        .locator("article")
        .filter({
          has: page.getByRole("heading", { name: title, exact: true }),
        })
        .getByRole("button", { name: "View campaign", exact: true })
        .click();
      await expect(
        page.getByRole("button", {
          name: "Edit name and description",
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Delete draft", exact: true }),
      ).toHaveCount(0);
    } finally {
      expect((await api.delete(`/campaigns/${record.id}`)).status()).toBe(204);
    }
  } finally {
    expect((await api.delete(`/leads/${lead.id}`)).status()).toBe(204);
  }
});
