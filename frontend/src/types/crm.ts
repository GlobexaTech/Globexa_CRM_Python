import type { components } from "@/api/generated";

type Schemas = components["schemas"];
export type Lead = Schemas["LeadResponse"];
export type LeadCreate = Schemas["LeadCreate"];
export type LeadUpdate = Schemas["LeadUpdate"];
export type Contact = Schemas["ContactResponse"];
export type ContactCreate = Schemas["ContactCreate"];
export type Company = Schemas["CompanyResponse"];
export type CompanyCreate = Schemas["CompanyCreate"];
export type Deal = Schemas["DealResponse"];
export type DealCreate = Schemas["DealCreate"];
export type DealUpdate = Schemas["DealUpdate"];
export type Pipeline = Schemas["PipelineResponse"];
export type PipelineStage = Schemas["StageResponse"];
export type Task = Schemas["TaskResponse"];
export type TaskCreate = Schemas["TaskCreate"];
export type Note = Schemas["NoteResponse"];
export type Activity = {
  id: string;
  subject: string;
  description?: string | null;
  type: string;
  created_at: string;
  lead_id?: string | null;
  contact_id?: string | null;
  company_id?: string | null;
  deal_id?: string | null;
};
export type User = Schemas["UserResponse"];
export type Job = Schemas["JobResponse"];
export type Paginated<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};
export type CustomerKind = "leads" | "contacts" | "companies";
// Customer360 uses a curated, generic response in OpenAPI. This mirrors customer.summary.
export type CustomerRecord = {
  id: string;
  name?: string;
  title?: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  subject?: string;
  content?: string;
  body?: string;
  description?: string;
  status?: string;
  value?: number;
  due_date?: string;
  created_at?: string;
  channel?: string;
  capability?: string;
  output?: Record<string, unknown>;
  conversation_id?: string;
  last_message_at?: string;
  [key: string]: unknown;
};
export type Customer360 = {
  customer: CustomerRecord;
  restricted_sections: string[];
  sections: Record<string, CustomerRecord[]>;
  timeline: {
    id: string;
    type: string;
    entity_id: string;
    occurred_at: string;
    version: number;
  }[];
  pagination: {
    limit: number;
    offset: number;
    has_more: boolean;
    section_limit: number;
  };
};
export const LEAD_STATUSES = [
  "new",
  "contacted",
  "qualified",
  "unqualified",
  "nurturing",
  "converted",
  "lost",
] as const;
export const LEAD_SOURCES = [
  "website",
  "meta_lead_ads",
  "facebook",
  "instagram",
  "linkedin",
  "google_ads",
  "csv_import",
  "whatsapp",
  "email_inbox",
  "apollo",
  "website_chatbot",
  "ai_lead_miner",
  "referral",
  "manual",
  "api",
  "webhook",
  "appointments",
  "partner_integration",
  "other",
] as const;
export const TASK_STATUSES = [
  "pending",
  "in_progress",
  "completed",
  "cancelled",
] as const;
export const TASK_PRIORITIES = ["low", "medium", "high", "urgent"] as const;
