import { api } from "@/api/client";
import type {
  AICapability,
  CampaignCreate,
  CampaignPlan,
  Conversation,
  ConversationInput,
  Job,
  WorkflowInput,
  Workflow,
} from "@/types/operations";

export const operations = {
  createConversation: (body: ConversationInput) =>
    api.post<Conversation>("/operations/conversations", body),
  readConversation: (id: string) =>
    api.post<{ unread_count: number }>(`/operations/conversations/${id}/read`),
  sendMessage: (
    id: string,
    body: { recipient: string; body: string },
    idempotencyKey: string,
  ) =>
    api.post<Job>(`/operations/conversations/${id}/messages`, body, {
      idempotencyKey,
    }),
  createCampaign: (body: CampaignCreate) =>
    api.post<{ id: string }>("/campaigns", body),
  updateCampaign: (id: string, body: Partial<CampaignCreate>) =>
    api.patch<{ id: string }>(`/campaigns/${id}`, body),
  deleteCampaign: (id: string) => api.delete<void>(`/campaigns/${id}`),
  planCampaign: (id: string, body: CampaignPlan) =>
    api.put<{ id: string; contacts: number; steps: number }>(
      `/operations/campaigns/${id}/plan`,
      body,
    ),
  transitionCampaign: (
    id: string,
    action: "launch" | "pause" | "resume" | "cancel",
  ) =>
    api.post<{ id: string; status: string }>(
      `/operations/campaigns/${id}/${action}`,
    ),
  scheduleCampaign: (id: string, scheduled_at: string) =>
    api.post<{ id: string; status: string }>(
      `/operations/campaigns/${id}/schedule`,
      { scheduled_at },
    ),
  saveWorkflow: (body: WorkflowInput, id?: string) =>
    id
      ? api.put<Workflow>(`/operations/workflows/${id}`, body)
      : api.post<Workflow>("/operations/workflows", body),
  toggleWorkflow: (id: string, enabled: boolean) =>
    api.patch<Workflow>(`/operations/workflows/${id}/enabled`, { enabled }),
  retryJob: (id: string) => api.post<Job>(`/operations/jobs/${id}/retry`),
  createIntegration: (provider: string, name: string) =>
    api.post<{ id: string }>("/integrations", {
      type: "email_inbox",
      name,
      config: { provider },
      sync_enabled: false,
      sync_frequency_minutes: 60,
    }),
  authorize: (id: string) =>
    api.post<{ authorization_url: string; expires_in: number }>(
      `/operations/integrations/${id}/authorize`,
    ),
  callback: (id: string, body: { state: string; code: string }) =>
    api.post<{ id: string; status: string }>(
      `/operations/integrations/${id}/callback`,
      body,
    ),
  refresh: (id: string) =>
    api.post<{ status: string }>(`/operations/integrations/${id}/refresh`),
  disconnect: (id: string) =>
    api.post<{ status: string; remote_revocation: boolean }>(
      `/operations/integrations/${id}/disconnect`,
    ),
  sync: (id: string, idempotencyKey: string, cursor?: string) =>
    api.post<Job>(
      `/operations/integrations/${id}/sync${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`,
      undefined,
      { idempotencyKey },
    ),
  ai: (capability: AICapability, entity_id: string, idempotencyKey: string) =>
    api.post<Job>(
      "/operations/ai/requests",
      { capability, entity_id },
      { idempotencyKey },
    ),
};

/** Legacy campaigns say sending; OPS says running. Display normalization only. */
export function campaignStatus(status: string) {
  return status === "sending" ? "running" : status;
}
export function choiceLabel(item: {
  id: string;
  title?: string;
  name?: string;
  first_name?: string;
  last_name?: string;
  email?: string;
}) {
  return (
    item.title ||
    item.name ||
    [item.first_name, item.last_name].filter(Boolean).join(" ") ||
    item.email ||
    item.id
  );
}
export function timestamp(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "Not recorded";
}

/** Form feedback only. Current actor, resource ownership and action permissions stay server-enforced. */
export function validateWorkflow(data: WorkflowInput): string | null {
  if (!data.name.trim()) return "Enter a workflow name.";
  if (
    !data.actions.length ||
    data.actions.length > 10 ||
    data.conditions.length > 20
  )
    return "Use 1–10 actions and at most 20 conditions.";
  for (const condition of data.conditions) {
    if (
      condition.field === "ai_score" &&
      (typeof condition.value !== "number" ||
        !Number.isFinite(condition.value) ||
        condition.value < 0 ||
        condition.value > 100)
    )
      return "AI score comparisons must be numbers from 0 to 100.";
    if (
      condition.field === "value" &&
      (typeof condition.value !== "number" ||
        !Number.isFinite(condition.value) ||
        condition.value < 0)
    )
      return "Deal value comparisons must be non-negative numbers in stored currency minor units.";
  }
  for (const action of data.actions) {
    const values = action.arguments;
    const required: Record<string, string[]> = {
      create_task: ["title"],
      add_note: ["content"],
      update_lead: ["entity_id"],
      update_deal: ["entity_id"],
      assign_owner: ["entity_id", "owner_id"],
      send_email: ["conversation_id", "recipient", "body"],
      invoke_ai: ["capability", "entity_id"],
    };
    if (!required[action.tool]) return "Choose an approved action.";
    if (
      required[action.tool].some((field) => !String(values[field] ?? "").trim())
    )
      return `Complete the required fields for ${action.tool.replaceAll("_", " ")}.`;
    if (
      ["create_task", "add_note"].includes(action.tool) &&
      !["lead_id", "contact_id", "deal_id", "company_id"].some(
        (field) => values[field],
      )
    )
      return "Each task or note action needs a customer relation.";
    if (
      ["update_lead", "update_deal"].includes(action.tool) &&
      !Object.entries(values).some(
        ([field, value]) => field !== "entity_id" && value !== "",
      )
    )
      return "An update action needs at least one changed field.";
    if (
      values.due_date &&
      (!/(Z|[+-]\d{2}:\d{2})$/.test(String(values.due_date)) ||
        !Number.isFinite(Date.parse(String(values.due_date))))
    )
      return "Task due dates must be valid ISO dates with a timezone.";
    if (
      values.value !== undefined &&
      values.value !== "" &&
      (!Number.isInteger(values.value) || Number(values.value) < 0)
    )
      return "Deal values must be non-negative whole currency minor units.";
  }
  return null;
}
