import { api } from "@/api/client";
import type {
  Lead,
  LeadCreate,
  LeadUpdate,
  Contact,
  ContactCreate,
  Company,
  CompanyCreate,
  Task,
  TaskCreate,
  Deal,
  DealCreate,
  DealUpdate,
  Pipeline,
  PipelineStage,
  Customer360,
  CustomerKind,
  Job,
} from "@/types/crm";

export function queryPath(
  path: string,
  values: Record<string, string | number | boolean | undefined | null>,
) {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== "" && value !== undefined && value !== null)
      query.set(key, String(value));
  });
  return `${path}?${query}`;
}
export const crm = {
  createLead: (body: LeadCreate) => api.post<Lead>("/leads", body),
  updateLead: (id: string, body: LeadUpdate) =>
    api.patch<Lead>(`/leads/${id}`, body),
  deleteLead: (id: string) => api.delete<void>(`/leads/${id}`),
  assignLead: (id: string, owner_id: string) =>
    api.post<Lead>(queryPath(`/leads/${id}/assign`, { owner_id })),
  createContact: (body: ContactCreate) => api.post<Contact>("/contacts", body),
  createCompany: (body: CompanyCreate) => api.post<Company>("/companies", body),
  createTask: (body: TaskCreate) => api.post<Task>("/tasks", body),
  createDeal: (body: DealCreate) => api.post<Deal>("/deals", body),
  updateDeal: (id: string, body: DealUpdate) =>
    api.patch<Deal>(`/deals/${id}`, body),
  moveDeal: (id: string, stage_id: string) =>
    api.post<Deal>(queryPath(`/deals/${id}/move`, { stage_id })),
  createPipeline: (name: string) =>
    api.post<Pipeline>("/deals/pipelines", { name }),
  createStage: (
    pipeline_id: string,
    name: string,
    order: number,
    probability: number,
    is_closed: boolean,
    is_won: boolean,
  ) =>
    api.post<PipelineStage>(`/deals/pipelines/${pipeline_id}/stages`, {
      pipeline_id,
      name,
      order,
      probability,
      is_closed,
      is_won,
    }),
  customer: (kind: CustomerKind, id: string) =>
    api.get<Customer360>(`/operations/customers/${kind}/${id}`),
  scoreLead: (id: string, key: string) =>
    api.post<Job>(
      "/operations/ai/requests",
      { capability: "lead_score", entity_id: id },
      { idempotencyKey: key },
    ),
};
export function displayName(value: {
  name?: string | null;
  title?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  full_name?: string | null;
  email?: string | null;
  id: string;
}) {
  return (
    value.name ||
    value.title ||
    [value.first_name, value.last_name].filter(Boolean).join(" ") ||
    value.full_name ||
    value.email ||
    value.id
  );
}
export function label(value: string) {
  return value.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
}
export function formatMoney(value: number, currency: string) {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
    }).format(value / 100);
  } catch {
    return `${currency} ${(value / 100).toFixed(2)}`;
  }
}
