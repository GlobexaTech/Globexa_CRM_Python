/** Generated schemas own stable DTOs; generic legacy/OPS dictionaries are explicit below. */
import type { components } from "@/api/generated";
type Schemas = components["schemas"];
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export interface LegacyPage<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
export interface Choice {
  id: string;
  title?: string;
  name?: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  email_opted_out?: boolean;
  do_not_contact?: boolean;
}
export type Conversation = Schemas["ConversationResponse"];
export type Participant = Schemas["ParticipantInput"];
export interface ConversationDetail {
  conversation: Conversation;
  participants: Participant[];
}
export interface Message {
  id: string;
  conversation_id: string;
  body: string;
  direction: string;
  status: string;
  sender: string | null;
  recipient: string | null;
  provider_message_id: string | null;
  attachments: { name: string; size?: number; content_type?: string }[];
  occurred_at: string;
  created_at: string;
}
export type Job = Schemas["JobResponse"];
export type ConversationInput = Schemas["ConversationInput"];
export interface Campaign {
  id: string;
  name: string;
  type: "broadcast" | "sequence" | "triggered";
  status: string;
  scheduled_at?: string | null;
  sender_name?: string;
  sender_email?: string;
  description?: string | null;
  audience?: { contact_ids: string[]; estimated_count: number } | null;
  templates?: { id: string; subject: string; step_order: number }[];
  sequences?: {
    id: string;
    delay_days: number;
    delay_hours: number;
    step_order: number;
  }[];
  stats?: Record<string, number> | null;
}
export interface CampaignCreate {
  name: string;
  type: Campaign["type"];
  sender_name: string;
  sender_email: string;
  description?: string;
}
export interface CampaignPlan {
  integration_id: string;
  contact_ids: string[];
  subject: string;
  body: string;
  steps: { subject: string; body: string; delay_hours: number }[];
  trigger_event?: string;
}
export interface Recipient {
  id: string;
  contact_id: string;
  contact_name?: string;
  email: string;
  status: string;
  sent_at?: string;
  error_message?: string;
  suppressed_reason?: string;
}
export interface CampaignStatistics {
  campaign_id: string;
  status: string;
  total_recipients: number;
  sent: number;
  queued: number;
  failed: number;
  suppressed: number;
  unknown?: number;
  opened: number;
  replied: number;
}
export const workflowTriggers = [
  "lead.created",
  "lead.updated",
  "deal.created",
  "deal.stage_changed",
  "task.overdue",
  "message.received",
  "campaign.completed",
] as const;
export const workflowTools = [
  "create_task",
  "update_lead",
  "update_deal",
  "add_note",
  "send_email",
  "assign_owner",
  "invoke_ai",
] as const;
export type WorkflowTool = (typeof workflowTools)[number];
export interface WorkflowCondition {
  field: "status" | "stage_id" | "ai_score" | "value" | "source" | "direction";
  operator: "eq" | "ne" | "gt" | "lt";
  value: string | number | boolean | null;
}
export interface WorkflowAction {
  tool: WorkflowTool;
  arguments: Record<string, string | number>;
}
export interface WorkflowInput {
  name: string;
  trigger: (typeof workflowTriggers)[number];
  conditions: WorkflowCondition[];
  actions: WorkflowAction[];
}
export interface Workflow {
  id: string;
  name: string;
  enabled: boolean;
  version: number;
}
export interface WorkflowDetail {
  id: string;
  enabled: boolean;
  version: number;
  definition: WorkflowInput | null;
}
export interface Execution {
  id: string;
  event_id: string;
  status: string;
  version: number;
  attempts: number;
  error_code: string | null;
  job_id?: string | null;
}
export interface Provider {
  provider: string;
  capabilities: string[];
  live_verified: boolean;
}
export interface Integration {
  id: string;
  name: string;
  type: string;
  status: string;
  sync_enabled: boolean;
  sync_frequency_minutes: number;
  last_sync_at: string | null;
  last_sync_status: string | null;
  records_synced: number;
}
export interface IntegrationStatus {
  id: string;
  status: string;
  capabilities: string[];
  expires_at: string | null;
  expired: boolean;
}
export interface SyncLog {
  id: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  records_processed?: number;
  records_created?: number;
  records_updated?: number;
  error_message?: string;
}
export const aiCapabilities = [
  {
    value: "lead_score",
    label: "Lead scoring",
    entity: "leads",
    permission: "ai:score_leads",
  },
  {
    value: "lead_summary",
    label: "Lead summary",
    entity: "leads",
    permission: "ai:read_leads",
  },
  {
    value: "next_best_action",
    label: "Next best action",
    entity: "deals",
    permission: "ai:change_stage",
  },
  {
    value: "reply_analysis",
    label: "Reply analysis",
    entity: "messages",
    permission: "ai:read_replies",
  },
  {
    value: "campaign_draft",
    label: "Campaign drafting",
    entity: "campaigns",
    permission: "ai:draft_email",
  },
  {
    value: "proposal_draft",
    label: "Proposal drafting",
    entity: "deals",
    permission: "ai:create_proposal",
  },
] as const;
export type AICapability = (typeof aiCapabilities)[number]["value"];
