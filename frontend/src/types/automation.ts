export type NodeType =
  | "condition"
  | "action"
  | "delay"
  | "ai"
  | "ai_decision"
  | "approval"
  | "intelligence";
export interface AutomationNode {
  id: string;
  type: NodeType;
  action?: string | null;
  arguments: Record<string, unknown>;
  condition?: Record<string, unknown> | null;
  next?: string | null;
  on_false?: string | null;
  on_error?: "stop" | "continue" | "fallback";
  fallback?: string | null;
  max_retries?: number;
  backoff_seconds?: number;
}
export interface Definition {
  trigger: string;
  nodes: AutomationNode[];
  variables?: Record<string, unknown>;
  credentials?: Record<string, string>;
  business_hours?: Record<string, unknown> | null;
  schedule?: Record<string, unknown> | null;
}
export interface Automation {
  id: string;
  name: string;
  description: string | null;
  status: string;
  version: number;
  draft: Definition;
}
export interface Step {
  id: string;
  node_key: string;
  state: string;
  attempts: number;
  retry_count: number;
  error_code: string | null;
  approval_id: string | null;
  input: Record<string, unknown>;
  result: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  resume_at: string | null;
}
export interface Execution {
  id: string;
  automation_id: string;
  version_id: string;
  state: string;
  current_node: string | null;
  step_count: number;
  ai_calls: number;
  error_code: string | null;
  correlation_id: string;
  created_at: string;
  resume_at: string | null;
  steps?: Step[];
}
export interface Property {
  type?: string;
  title?: string;
  format?: string;
  enum?: string[];
  anyOf?: Property[];
  default?: unknown;
}
export interface Catalog {
  triggers: string[];
  actions: Record<
    string,
    { properties: Record<string, Property>; required?: string[] }
  >;
  node_types: NodeType[];
  limits: Record<string, number | boolean>;
}
