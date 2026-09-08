"use client";
import type { ReactNode } from "react";
export function ResourceState({
  loading,
  error,
  empty,
  onRetry,
  children,
}: {
  loading: boolean;
  error: unknown;
  empty?: boolean;
  onRetry?: () => unknown;
  children?: ReactNode;
}) {
  if (loading)
    return (
      <div className="card p-6" role="status">
        Loading workspace data…
      </div>
    );
  if (error)
    return (
      <div className="card p-6 crm-error" role="alert">
        <p>{error instanceof Error ? error.message : String(error)}</p>
        {onRetry && (
          <button className="crm-secondary mt-3" onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    );
  if (empty)
    return (
      <div className="card p-6 crm-muted" role="status">
        No matching records. Add a record or change your filters.
      </div>
    );
  return <>{children}</>;
}
