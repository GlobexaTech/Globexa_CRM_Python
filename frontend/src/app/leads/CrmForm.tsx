"use client";
import { useState, type FormEvent } from "react";
import { api } from "@/api/client";
import { useSession } from "@/auth/SessionProvider";
import { useAction } from "@/hooks/useAction";
import { Field, EntityPicker, EnumField, control, primary } from "./CrmFields";
import type {
  Lead,
  Contact,
  Company,
  Task,
  LeadCreate,
  TaskCreate,
} from "@/types/crm";
import {
  LEAD_STATUSES,
  LEAD_SOURCES,
  TASK_STATUSES,
  TASK_PRIORITIES,
} from "@/types/crm";

type Kind = "leads" | "contacts" | "companies" | "tasks";
type RecordType = Lead | Contact | Company | Task;
function localDate(value: unknown) {
  if (typeof value !== "string" || !value) return "";
  const date = new Date(value);
  if (Number.isNaN(+date)) return "";
  return new Date(+date - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
export default function CrmForm({
  kind,
  record,
  onSaved,
  relation,
}: {
  kind: Kind;
  record?: RecordType;
  onSaved: () => void;
  relation?: { key: string; id: string };
}) {
  const { session } = useSession();
  const action = useAction();
  const original = (record ?? {}) as Record<string, unknown>;
  const [values, setValues] = useState<Record<string, string | boolean>>(
    () => ({
      title: String(original.title ?? ""),
      first_name: String(original.first_name ?? ""),
      last_name: String(original.last_name ?? ""),
      name: String(original.name ?? ""),
      description: String(original.description ?? ""),
      email: String(original.email ?? ""),
      phone: String(original.phone ?? ""),
      domain: String(original.domain ?? ""),
      industry: String(original.industry ?? ""),
      website: String(original.website ?? ""),
      size: String(original.size ?? ""),
      revenue: String(original.revenue ?? ""),
      status: String(original.status ?? (kind === "tasks" ? "pending" : "new")),
      priority: String(original.priority ?? "medium"),
      source: String(original.source ?? (kind === "leads" ? "manual" : "")),
      owner_id: String(original.owner_id ?? session?.user?.id ?? ""),
      contact_id: String(original.contact_id ?? ""),
      company_id: String(original.company_id ?? ""),
      lead_id: String(original.lead_id ?? ""),
      deal_id: String(original.deal_id ?? ""),
      due_date: localDate(original.due_date),
      do_not_contact: Boolean(original.do_not_contact),
      email_opted_out: Boolean(original.email_opted_out),
      sms_opted_out: Boolean(original.sms_opted_out),
      ...(relation ? { [relation.key]: relation.id } : {}),
    }),
  );
  const [validation, setValidation] = useState("");
  const text = (key: string) => String(values[key] ?? "");
  const set = (key: string, value: string | boolean) =>
    setValues((old) => ({ ...old, [key]: value }));
  const nullable = (key: string) => text(key).trim() || null;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setValidation("");
    const requiredFields =
      kind === "contacts"
        ? ["first_name", "last_name"]
        : kind === "companies"
          ? ["name"]
          : ["title"];
    if (requiredFields.some((key) => !text(key).trim())) {
      setValidation("Required fields cannot contain only spaces.");
      return;
    }
    if (
      kind === "tasks" &&
      !["lead_id", "contact_id", "company_id", "deal_id"].some((key) =>
        text(key),
      )
    ) {
      setValidation(
        "Choose at least one lead, contact, company or deal for this task.",
      );
      return;
    }
    let body: object;
    if (kind === "leads") {
      const value: LeadCreate = {
        custom_fields: (original.custom_fields ??
          {}) as LeadCreate["custom_fields"],
        title: text("title").trim(),
        description: nullable("description"),
        contact_id: nullable("contact_id"),
        company_id: nullable("company_id"),
        owner_id: nullable("owner_id"),
        status: text("status") as LeadCreate["status"],
        source: nullable("source") as LeadCreate["source"],
      };
      body = value;
    } else if (kind === "contacts")
      body = {
        first_name: text("first_name").trim(),
        last_name: text("last_name").trim(),
        email: nullable("email"),
        phone: nullable("phone"),
        company_id: nullable("company_id"),
        title: nullable("title"),
        do_not_contact: values.do_not_contact,
        email_opted_out: values.email_opted_out,
        sms_opted_out: values.sms_opted_out,
      };
    else if (kind === "companies")
      body = {
        name: text("name").trim(),
        domain: nullable("domain"),
        industry: nullable("industry"),
        website: nullable("website"),
        description: nullable("description"),
        size: nullable("size"),
        revenue: text("revenue") ? Number(text("revenue")) : null,
        source: nullable("source"),
      };
    else {
      const value: TaskCreate = {
        is_recurring: Boolean(original.is_recurring),
        custom_fields: (original.custom_fields ??
          {}) as TaskCreate["custom_fields"],
        title: text("title").trim(),
        description: nullable("description"),
        status: text("status") as TaskCreate["status"],
        priority: text("priority") as TaskCreate["priority"],
        owner_id: nullable("owner_id"),
        lead_id: nullable("lead_id"),
        deal_id: nullable("deal_id"),
        contact_id: nullable("contact_id"),
        company_id: nullable("company_id"),
        due_date: text("due_date")
          ? new Date(text("due_date")).toISOString()
          : null,
      };
      body = value;
    }
    await action.run(async () => {
      if (record) await api.patch(`/${kind}/${record.id}`, body);
      else await api.post(`/${kind}`, body);
      onSaved();
    });
  }
  const input = (
    key: string,
    title: string,
    required = false,
    type = "text",
    maxLength = 255,
  ) => (
    <Field title={title}>
      <input
        className={control}
        name={key}
        value={text(key)}
        onChange={(e) => set(key, e.target.value)}
        required={required}
        type={type}
        maxLength={maxLength}
        min={type === "number" ? 0 : undefined}
      />
    </Field>
  );
  return (
    <form onSubmit={submit} className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {kind === "contacts" ? (
          <>
            {input("first_name", "First name", true)}
            {input("last_name", "Last name", true)}
            {input("email", "Email", false, "email")}
            {input("phone", "Phone")}
            {input("title", "Job title")}
          </>
        ) : kind === "companies" ? (
          <>
            {input("name", "Company name", true)}
            {input("domain", "Domain")}
            {input("industry", "Industry")}
            {input("website", "Website", false, "url")}
            {input("size", "Company size")}
            {input("revenue", "Annual revenue", false, "number")}
            {input("source", "Source")}
          </>
        ) : (
          input("title", kind === "leads" ? "Lead title" : "Task title", true)
        )}
        {(kind === "leads" || kind === "tasks") && (
          <EnumField
            title="Status"
            value={text("status")}
            options={kind === "leads" ? LEAD_STATUSES : TASK_STATUSES}
            onChange={(v) => set("status", v)}
          />
        )}
        {kind === "leads" && (
          <EnumField
            title="Source"
            value={text("source")}
            options={LEAD_SOURCES}
            blank="Not specified"
            onChange={(v) => set("source", v)}
          />
        )}
        {kind === "tasks" && (
          <>
            <EnumField
              title="Priority"
              value={text("priority")}
              options={TASK_PRIORITIES}
              onChange={(v) => set("priority", v)}
            />
            {input("due_date", "Due date and time", false, "datetime-local")}
          </>
        )}
      </div>
      {kind !== "contacts" && (
        <Field title="Description">
          <textarea
            className={control}
            rows={3}
            value={text("description")}
            onChange={(e) => set("description", e.target.value)}
          />
        </Field>
      )}
      {kind === "contacts" && (
        <fieldset className="grid gap-2">
          <legend className="mb-2 font-medium">Contact preferences</legend>
          {(
            ["do_not_contact", "email_opted_out", "sms_opted_out"] as const
          ).map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={Boolean(values[key])}
                onChange={(e) => set(key, e.target.checked)}
              />
              {key === "do_not_contact"
                ? "Do not contact"
                : key === "email_opted_out"
                  ? "Email opted out"
                  : "SMS opted out"}
            </label>
          ))}
        </fieldset>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {kind !== "companies" && (
          <EntityPicker
            entity="companies"
            title="Company"
            value={text("company_id")}
            onChange={(v) => set("company_id", v)}
          />
        )}{" "}
        {(kind === "leads" || kind === "tasks") && (
          <EntityPicker
            entity="contacts"
            title="Contact"
            value={text("contact_id")}
            onChange={(v) => set("contact_id", v)}
          />
        )}
        {(kind === "leads" || kind === "tasks") && (
          <EntityPicker
            entity="users"
            title="Owner"
            value={text("owner_id")}
            onChange={(v) => set("owner_id", v)}
          />
        )}
        {kind === "tasks" && (
          <>
            <EntityPicker
              entity="leads"
              title="Lead"
              value={text("lead_id")}
              onChange={(v) => set("lead_id", v)}
            />
            <EntityPicker
              entity="deals"
              title="Deal"
              value={text("deal_id")}
              onChange={(v) => set("deal_id", v)}
            />
          </>
        )}
      </div>
      {validation && (
        <p role="alert" className="text-sm text-red-700">
          {validation}
        </p>
      )}
      {action.error && (
        <p role="alert" className="text-sm text-red-700">
          {action.error}
        </p>
      )}
      <button className={primary} disabled={action.pending} type="submit">
        {action.pending
          ? "Saving…"
          : record
            ? "Save changes"
            : `Create ${kind === "companies" ? "company" : kind.slice(0, -1)}`}
      </button>
    </form>
  );
}
