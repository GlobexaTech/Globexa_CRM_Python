/** Workforce responses are tenant-filtered by the backend; never accept actor overrides. */
export interface WorkforceAgent {
  name: string;
  label: string;
  tools: string[];
}
export interface WorkforceContext {
  entity_type?: "lead" | "contact" | "deal" | "conversation" | "campaign";
  entity_id?: string;
  untrusted_text?: string;
  research_urls?: string[];
}
export interface WorkforceTask {
  agent_name: string;
  objective: string;
  context: WorkforceContext;
  tools: string[];
}
export interface AgentExecution {
  id: string;
  agent_name: string;
  task_type: string;
  state: "queued" | "running" | "completed" | "failed" | "cancelled";
  task: Omit<WorkforceTask, "agent_name">;
  tools_used: string[];
  result: Record<string, unknown> | null;
  error_message: string | null;
  model: string | null;
  provider: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  parent_id: string | null;
  attempts: number;
  cancel_requested: boolean;
  children?: AgentExecution[];
}
export interface Approval {
  id: string;
  agent_name: string;
  requesting_user_id: string | null;
  execution_id: string | null;
  action_type: string;
  target: string | null;
  proposed_action: Record<string, unknown>;
  action_hash: string;
  status:
    | "pending"
    | "approved"
    | "rejected"
    | "expired"
    | "executed"
    | "failed";
  created_at: string;
  expires_at: string | null;
  decided_at: string | null;
  decided_by: string | null;
  rejection_reason: string | null;
  execution_result: Record<string, unknown> | null;
}
export interface AgentMemory {
  id: string;
  agent_name: string;
  memory_type: string;
  key: string;
  value: unknown;
  actor_id: string | null;
  approved_by: string | null;
  execution_id: string | null;
  created_at: string;
  expires_at: string | null;
}
