import { api } from "@/api/client";
import type { components } from "@/api/generated";
export type Schema = components["schemas"];
export type User = Schema["UserResponse"];
export type Tenant = Schema["TenantWithSubscription"];
export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};
export type Summary = {
  id: string;
  title?: string;
  subject?: string;
  name?: string;
  description?: string;
  content?: string;
  due_date?: string;
  created_at?: string;
  capability?: string;
  output?: Record<string, unknown>;
  status?: string;
};
export type PipelineMetric = {
  id: string;
  name: string;
  deals: number;
  value: number;
  currency: string | null;
};
export type Dashboard = {
  leads: number;
  deals: number;
  open_tasks: number;
  completed_tasks: number;
  pending_jobs: number;
  failed_jobs: number;
  generated_at: string;
  tasks: Summary[];
  activities: Summary[];
  ai_insights?: Summary[];
  pipeline: PipelineMetric[];
};
export type AnalyticsView =
  "dashboard" | "pipeline" | "conversion" | "campaigns" | "activity" | "ai";
export type Analytics = Partial<Dashboard> & {
  stages?: PipelineMetric[];
  converted?: number;
  conversion_rate?: number;
  delivery_status?: Record<string, number>;
  events?: Record<string, number>;
  first_response_seconds?: number | null;
  response_sample_count?: number;
  response_window?: string;
  usage?: {
    success: boolean;
    requests: number;
    tokens: number;
    known_cost_usd: number | null;
    unpriced_requests: number;
  }[];
};
export const analyticsPermissions: Record<AnalyticsView, string[]> = {
  dashboard: ["analytics:read", "leads:read", "deals:read", "tasks:read"],
  pipeline: ["analytics:read", "deals:read"],
  conversion: ["analytics:read", "leads:read"],
  campaigns: ["analytics:read", "campaigns:analytics"],
  activity: ["analytics:read", "tasks:read", "conversations:read"],
  ai: ["analytics:read", "ai:chat"],
};
export const workspace = {
  updateProfile: (data: Schema["UserUpdate"]) =>
    api.patch<User>("/auth/me", data),
  updateTenant: (id: string, data: Schema["TenantUpdate"]) =>
    api.patch<Tenant>(`/tenants/${id}`, data),
  createUser: (data: Schema["UserCreate"]) => api.post<User>("/users", data),
  role: (id: string, role: string) =>
    api.patch(`/users/${id}/memberships`, { role }),
  removeUser: (id: string) => api.delete(`/users/${id}`),
};
export function money(minor: number, currency: string | null) {
  return currency
    ? new Intl.NumberFormat(undefined, { style: "currency", currency }).format(
        minor / 100,
      )
    : "—";
}
export function localTime(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "Not set";
}
