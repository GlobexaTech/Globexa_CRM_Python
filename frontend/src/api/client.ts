"use client";

export interface RequestOptions { signal?: AbortSignal; idempotencyKey?: string; timeoutMs?: number }
export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string, public retryAfter?: number, public fields?: Record<string, string>) {
    super(message);
    this.name = "ApiError";
  }
}

let workspaceVersion: string | null = null;
let sessionFailure: ((status: number, code?: string) => void) | undefined;
const active = new Set<AbortController>();

export function cancelRequests() {
  for (const controller of active) controller.abort();
  active.clear();
}

export function configureSession(version: string | null, onFailure?: (status: number, code?: string) => void) {
  if (workspaceVersion !== version) cancelRequests();
  workspaceVersion = version;
  if (onFailure) sessionFailure = onFailure;
}

export async function decodeResponse<T>(response: Response): Promise<T> {
  const body: unknown = response.status === 204 ? undefined : await response.json().catch(() => undefined);
  if (response.ok) return body as T;
  const error = body && typeof body === "object" ? body as { detail?: unknown; code?: string; message?: string; errors?: { loc?: (string | number)[]; type?: string }[] } : {};
  const detail = error.detail;
  let message = error.message || "The request could not be completed.";
  let code = error.code;
  let fields: Record<string, string> | undefined;
  if (typeof detail === "string") message = detail;
  else if (Array.isArray(detail)) {
    fields = Object.fromEntries(detail.map((item: { loc?: (string | number)[]; msg?: string }) => [(item.loc ?? []).filter((part) => part !== "body").join("."), item.msg ?? "Invalid value"]));
    message = Object.values(fields).join("; ") || "Please check the highlighted fields.";
  } else if (detail && typeof detail === "object") {
    const value = detail as { message?: string; code?: string; error?: string };
    message = value.message ?? value.error ?? message;
    code = value.code ?? code;
  }
  if (Array.isArray(error.errors)) {
    fields = Object.fromEntries(error.errors.map((item) => [(item.loc ?? []).filter((part) => part !== "body").join("."), (item.type ?? "Invalid value").replaceAll("_", " ")]));
    message = "Please check these fields: " + Object.keys(fields).join(", ");
  }
  const retry = response.headers.get("retry-after");
  const retryAfter = retry ? Math.max(0, Number.isFinite(Number(retry)) ? Number(retry) : Math.ceil((Date.parse(retry) - Date.now()) / 1000)) : undefined;
  throw new ApiError(response.status, message, code, Number.isFinite(retryAfter) ? retryAfter : undefined, fields);
}

async function request<T>(method: string, path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("#")) throw new ApiError(400, "Invalid API path.", "invalid_path");
  const version = workspaceVersion;
  if (!version) throw new ApiError(401, "Please sign in again.", "session_expired");
  const controller = new AbortController();
  let timedOut = false;
  const timeoutMs = Number.isFinite(options.timeoutMs) ? Math.max(1, Math.min(options.timeoutMs!, 120000)) : 30000;
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  const cancel = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  options.signal?.addEventListener("abort", cancel, { once: true });
  active.add(controller);
  try {
    const response = await fetch(`/api/crm${path}`, {
      method, credentials: "same-origin", cache: "no-store", signal: controller.signal,
      headers: { "Content-Type": "application/json", "X-Workspace-Version": version, ...(options.idempotencyKey ? { "Idempotency-Key": options.idempotencyKey } : {}) },
      ...(!["GET", "DELETE"].includes(method) ? { body: JSON.stringify(body ?? {}) } : {}),
    });
    if (timedOut) throw new ApiError(408, "This request timed out. Check the operation status before retrying a change.", "timeout");
    if (version !== workspaceVersion) throw new ApiError(409, "Your workspace changed. Reload this view.", "workspace_changed");
    const data = await decodeResponse<T>(response);
    if (version !== workspaceVersion || response.headers.get("x-workspace-version") !== version) throw new ApiError(409, "Your workspace changed. Reload this view.", "workspace_changed");
    return data;
  } catch (error) {
    if (timedOut) throw new ApiError(408, "This request timed out. Check the operation status before retrying a change.", "timeout");
    if (error instanceof ApiError) {
      if (version === workspaceVersion && (error.status === 401 || error.code === "workspace_changed")) sessionFailure?.(error.status, error.code);
      throw error;
    }
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError(0, "The network request failed. Check the operation status before retrying a change.", "network_error");
  } finally {
    clearTimeout(timeout);
    active.delete(controller);
    options.signal?.removeEventListener("abort", cancel);
  }
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>("GET", path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>("POST", path, body, options),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>("PUT", path, body, options),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>("PATCH", path, body, options),
  delete: <T>(path: string, options?: RequestOptions) => request<T>("DELETE", path, undefined, options),
};
