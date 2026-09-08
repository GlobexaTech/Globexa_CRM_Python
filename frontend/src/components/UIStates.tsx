"use client";

import {
  Inbox,
  Plus,
} from "lucide-react";

import type {
  ReactNode,
} from "react";

type EmptyStateProps = {
  icon?: ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
};

export function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
}: EmptyStateProps) {
  return (
    <div className="globexa-empty-state">
      <div className="globexa-empty-icon">
        {icon || (
          <Inbox size={22} />
        )}
      </div>

      <h3 className="globexa-empty-title">
        {title}
      </h3>

      <p className="globexa-empty-description">
        {description}
      </p>

      {actionLabel &&
        onAction && (
          <button
            type="button"
            onClick={onAction}
            className="globexa-empty-action"
          >
            <Plus size={15} />
            {actionLabel}
          </button>
        )}
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="globexa-page-skeleton">
      <div className="globexa-skeleton globexa-skeleton-eyebrow" />

      <div className="globexa-skeleton globexa-skeleton-title" />

      <div className="globexa-skeleton globexa-skeleton-subtitle" />

      <div className="globexa-skeleton-grid">
        {Array.from({
          length: 4,
        }).map((_, index) => (
          <div
            key={index}
            className="globexa-skeleton-card"
          >
            <div className="globexa-skeleton globexa-skeleton-small" />

            <div className="globexa-skeleton globexa-skeleton-value" />

            <div className="globexa-skeleton globexa-skeleton-small-short" />
          </div>
        ))}
      </div>

      <div className="globexa-skeleton-panel">
        <div className="globexa-skeleton globexa-skeleton-panel-title" />

        {Array.from({
          length: 4,
        }).map((_, index) => (
          <div
            key={index}
            className="globexa-skeleton-row"
          >
            <div className="globexa-skeleton globexa-skeleton-row-name" />

            <div className="globexa-skeleton globexa-skeleton-row-data" />

            <div className="globexa-skeleton globexa-skeleton-row-data" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function InlineSkeleton({
  width = "100%",
  height = 16,
}: {
  width?: string | number;
  height?: number;
}) {
  return (
    <div
      className="globexa-skeleton"
      style={{
        width,
        height,
      }}
    />
  );
}