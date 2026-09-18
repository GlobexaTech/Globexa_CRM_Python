"use client";
import { useEffect, useRef, useState } from "react";
import type {
  Automation,
  AutomationNode,
  Catalog,
  Definition,
  NodeType,
} from "@/types/automation";

const label = (value: string) => value.replaceAll("_", " ");
function initialNode(type: NodeType, index: number): AutomationNode {
  return {
    id: `step_${index}`,
    type,
    arguments:
      type === "delay"
        ? { minutes: 5 }
        : type === "approval"
          ? { reason: "Review before continuing" }
          : type === "intelligence"
            ? { kind: "lead" }
            : {},
    ...(type === "action"
      ? {
          action: "create_notification",
          arguments: { message: "Workflow completed" },
        }
      : {}),
    ...(type === "condition"
      ? { condition: { field: "lead.score", operator: "gte", value: 50 } }
      : {}),
  };
}

export function AutomationBuilder({
  workflow,
  catalog,
  disabled,
  onSave,
}: {
  workflow?: Automation;
  catalog: Catalog;
  disabled: boolean;
  onSave: (value: {
    name: string;
    description: string;
    definition: Definition;
  }) => Promise<void>;
}) {
  const [name, setName] = useState(workflow?.name ?? "");
  const [description, setDescription] = useState(workflow?.description ?? "");
  const [definition, setDefinition] = useState<Definition>(
    workflow?.draft ?? { trigger: "manual", nodes: [initialNode("action", 1)] },
  );
  const [newType, setNewType] = useState<NodeType>("action");
  const [variables, setVariables] = useState(
    JSON.stringify(definition.variables ?? {}, null, 2),
  );
  const [credentials, setCredentials] = useState(
    JSON.stringify(definition.credentials ?? {}, null, 2),
  );
  const [hours, setHours] = useState(
    JSON.stringify(definition.business_hours ?? null, null, 2),
  );
  const [schedule, setSchedule] = useState(
    JSON.stringify(
      definition.schedule ?? {
        kind: "daily",
        timezone: "Asia/Kolkata",
        time: "09:00",
      },
      null,
      2,
    ),
  );
  const [error, setError] = useState("");
  function patch(index: number, value: Partial<AutomationNode>) {
    setDefinition({
      ...definition,
      nodes: definition.nodes.map((node, i) =>
        i === index ? { ...node, ...value } : node,
      ),
    });
  }
  function move(index: number, delta: number) {
    const nodes = [...definition.nodes];
    [nodes[index], nodes[index + delta]] = [nodes[index + delta], nodes[index]];
    setDefinition({ ...definition, nodes });
  }
  return (
    <form
      className="space-y-4"
      onSubmit={async (event) => {
        event.preventDefault();
        setError("");
        try {
          await onSave({
            name,
            description,
            definition: {
              ...definition,
              variables: JSON.parse(variables),
              credentials: JSON.parse(credentials),
              business_hours: JSON.parse(hours),
              schedule:
                definition.trigger === "scheduled"
                  ? JSON.parse(schedule)
                  : null,
            },
          });
        } catch (failure) {
          setError(
            failure instanceof Error
              ? failure.message
              : "Check the workflow fields.",
          );
        }
      }}
    >
      <fieldset disabled={disabled} className="space-y-4">
        <label className="crm-field">
          Workflow name
          <input
            className="crm-input"
            required
            maxLength={255}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="crm-field">
          Description
          <textarea
            className="crm-input"
            maxLength={2000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label className="crm-field">
          Trigger
          <select
            className="crm-input"
            value={definition.trigger}
            onChange={(e) =>
              setDefinition({ ...definition, trigger: e.target.value })
            }
          >
            {catalog.triggers.map((trigger) => (
              <option key={trigger}>{trigger}</option>
            ))}
          </select>
        </label>
        {definition.trigger === "scheduled" && (
          <label className="crm-field">
            Schedule (timezone and recurrence)
            <textarea
              className="crm-input font-mono"
              rows={6}
              value={schedule}
              onChange={(e) => setSchedule(e.target.value)}
            />
            <small>
              Use once, daily, weekly, monthly or cron with an IANA timezone. A
              one-time schedule needs an ISO date in at.
            </small>
          </label>
        )}
        <ol className="space-y-4" aria-label="Workflow steps">
          {definition.nodes.map((node, index) => {
            const spec = node.action ? catalog.actions[node.action] : undefined;
            return (
              <li
                className="card space-y-3 border-l-4 border-[var(--blue)] p-4"
                key={node.id}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-semibold">
                    {index + 1}. {label(node.type)} · {node.id}
                  </h3>
                  <div className="crm-actions">
                    <button
                      className="crm-secondary"
                      type="button"
                      disabled={index === 0}
                      onClick={() => move(index, -1)}
                      aria-label={`Move ${node.id} up`}
                    >
                      ↑
                    </button>
                    <button
                      className="crm-secondary"
                      type="button"
                      disabled={index === definition.nodes.length - 1}
                      onClick={() => move(index, 1)}
                      aria-label={`Move ${node.id} down`}
                    >
                      ↓
                    </button>
                    <button
                      className="crm-secondary"
                      type="button"
                      disabled={definition.nodes.length === 1}
                      onClick={() =>
                        setDefinition({
                          ...definition,
                          nodes: definition.nodes.filter((_, i) => i !== index),
                        })
                      }
                    >
                      Remove {node.id}
                    </button>
                  </div>
                </div>
                {node.type === "action" && (
                  <>
                    <label className="crm-field">
                      Action
                      <select
                        className="crm-input"
                        value={node.action ?? ""}
                        onChange={(e) =>
                          patch(index, {
                            action: e.target.value,
                            arguments: {},
                          })
                        }
                      >
                        {Object.keys(catalog.actions).map((action) => (
                          <option key={action} value={action}>
                            {label(action)}
                          </option>
                        ))}
                      </select>
                    </label>
                    {Object.entries(spec?.properties ?? {})
                      .filter(([field]) => field !== "attachments")
                      .map(([field, property]) => (
                        <label className="crm-field" key={field}>
                          {label(field)}
                          {spec?.required?.includes(field) ? " *" : ""}
                          {property.type === "object" ? (
                            <JsonField
                              value={node.arguments[field] ?? {}}
                              onChange={(value) =>
                                patch(index, {
                                  arguments: {
                                    ...node.arguments,
                                    [field]: value,
                                  },
                                })
                              }
                            />
                          ) : (
                            <input
                              className="crm-input"
                              required={spec?.required?.includes(field)}
                              value={String(node.arguments[field] ?? "")}
                              onChange={(e) =>
                                patch(index, {
                                  arguments: {
                                    ...node.arguments,
                                    [field]: e.target.value,
                                  },
                                })
                              }
                            />
                          )}
                        </label>
                      ))}
                  </>
                )}
                {node.type === "condition" && (
                  <Condition
                    value={node.condition ?? {}}
                    onChange={(condition) => patch(index, { condition })}
                  />
                )}
                {node.type === "delay" && (
                  <label className="crm-field">
                    Wait minutes
                    <input
                      className="crm-input"
                      type="number"
                      min={0}
                      max={43200}
                      value={Number(node.arguments.minutes ?? 0)}
                      onChange={(e) =>
                        patch(index, {
                          arguments: { minutes: Number(e.target.value) },
                        })
                      }
                    />
                    <small>Advanced wait modes are available below.</small>
                  </label>
                )}
                {(node.type === "ai" || node.type === "ai_decision") && (
                  <>
                    <label className="crm-field">
                      Analysis type
                      <select
                        className="crm-input"
                        value={String(node.arguments.kind ?? "summarize")}
                        onChange={(e) =>
                          patch(index, {
                            arguments: {
                              ...node.arguments,
                              kind: e.target.value,
                            },
                          })
                        }
                      >
                        {[
                          "summarize",
                          "classify",
                          "score",
                          "recommend",
                          "research",
                          "draft",
                          "extract",
                        ].map((kind) => (
                          <option key={kind}>{kind}</option>
                        ))}
                      </select>
                    </label>
                    <label className="crm-field">
                      Instructions
                      <textarea
                        className="crm-input"
                        maxLength={2000}
                        value={String(node.arguments.instruction ?? "")}
                        onChange={(e) =>
                          patch(index, {
                            arguments: {
                              ...node.arguments,
                              instruction: e.target.value,
                            },
                          })
                        }
                      />
                    </label>
                    {node.arguments.kind === "research" && (
                      <label className="crm-field">
                        Public source URL
                        <input
                          className="crm-input"
                          type="url"
                          value={String(node.arguments.url ?? "")}
                          onChange={(e) =>
                            patch(index, {
                              arguments: {
                                ...node.arguments,
                                url: e.target.value,
                              },
                            })
                          }
                        />
                      </label>
                    )}
                    <p className="crm-muted">
                      AI results are recommendations. Actions using them require
                      independent approval.
                    </p>
                  </>
                )}
                {node.type === "approval" && (
                  <label className="crm-field">
                    Approval reason
                    <input
                      className="crm-input"
                      required
                      value={String(node.arguments.reason ?? "")}
                      onChange={(e) =>
                        patch(index, { arguments: { reason: e.target.value } })
                      }
                    />
                  </label>
                )}
                {node.type === "intelligence" && (
                  <label className="crm-field">
                    Intelligence type
                    <select
                      className="crm-input"
                      value={String(node.arguments.kind ?? "lead")}
                      onChange={(e) =>
                        patch(index, { arguments: { kind: e.target.value } })
                      }
                    >
                      {[
                        "lead",
                        "deal",
                        "customer",
                        "campaign",
                        "next_best_action",
                      ].map((kind) => (
                        <option key={kind}>{kind}</option>
                      ))}
                    </select>
                  </label>
                )}
                <label className="crm-field">
                  Next step
                  <select
                    className="crm-input"
                    value={node.next ?? ""}
                    onChange={(e) =>
                      patch(index, { next: e.target.value || null })
                    }
                  >
                    <option value="">Next in order</option>
                    {definition.nodes
                      .filter((n) => n.id !== node.id)
                      .map((n) => (
                        <option key={n.id}>{n.id}</option>
                      ))}
                  </select>
                </label>
                {(node.type === "condition" || node.type === "ai_decision") && (
                  <label className="crm-field">
                    When false
                    <select
                      className="crm-input"
                      value={node.on_false ?? ""}
                      onChange={(e) =>
                        patch(index, { on_false: e.target.value || null })
                      }
                    >
                      <option value="">Finish workflow</option>
                      {definition.nodes
                        .filter((n) => n.id !== node.id)
                        .map((n) => (
                          <option key={n.id}>{n.id}</option>
                        ))}
                    </select>
                  </label>
                )}
                <details>
                  <summary className="cursor-pointer">
                    Failure handling and advanced arguments
                  </summary>
                  <div className="mt-3 space-y-3">
                    <label className="crm-field">
                      On failure
                      <select
                        className="crm-input"
                        value={node.on_error ?? "stop"}
                        onChange={(e) =>
                          patch(index, {
                            on_error: e.target
                              .value as AutomationNode["on_error"],
                          })
                        }
                      >
                        {["stop", "continue", "fallback"].map((value) => (
                          <option key={value}>{value}</option>
                        ))}
                      </select>
                    </label>
                    {node.on_error === "fallback" && (
                      <label className="crm-field">
                        Fallback action
                        <select
                          className="crm-input"
                          required
                          value={node.fallback ?? ""}
                          onChange={(e) =>
                            patch(index, { fallback: e.target.value })
                          }
                        >
                          <option value="">Select action</option>
                          {definition.nodes
                            .filter(
                              (n) => n.type === "action" && n.id !== node.id,
                            )
                            .map((n) => (
                              <option key={n.id}>{n.id}</option>
                            ))}
                        </select>
                      </label>
                    )}
                    <label className="crm-field">
                      Maximum retries
                      <input
                        className="crm-input"
                        type="number"
                        min={0}
                        max={5}
                        value={node.max_retries ?? 2}
                        onChange={(e) =>
                          patch(index, { max_retries: Number(e.target.value) })
                        }
                      />
                    </label>
                    <label className="crm-field">
                      Arguments
                      <JsonField
                        value={node.arguments}
                        onChange={(arguments_) =>
                          patch(index, {
                            arguments: arguments_ as Record<string, unknown>,
                          })
                        }
                      />
                    </label>
                  </div>
                </details>
              </li>
            );
          })}
        </ol>
        <div className="crm-actions">
          <label className="crm-field">
            New step type
            <select
              className="crm-input"
              value={newType}
              onChange={(e) => setNewType(e.target.value as NodeType)}
            >
              {catalog.node_types.map((type) => (
                <option key={type}>{type}</option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="crm-secondary"
            disabled={definition.nodes.length >= 100}
            onClick={() => {
              let index = definition.nodes.length + 1;
              while (definition.nodes.some((n) => n.id === `step_${index}`))
                index++;
              setDefinition({
                ...definition,
                nodes: [...definition.nodes, initialNode(newType, index)],
              });
            }}
          >
            Add step
          </button>
        </div>
        <details>
          <summary className="cursor-pointer">
            Variables, provider references and business hours
          </summary>
          <p className="crm-muted my-3">
            Insert named values such as {"{{lead.id}}"} or{" "}
            {"{{steps.step_1.score}}"}. Provider references contain integration
            IDs; keep credentials in Integrations.
          </p>
          {[
            ["Variables", variables, setVariables],
            ["Provider references", credentials, setCredentials],
            ["Business hours", hours, setHours],
          ].map(([title, value, setter]) => (
            <label className="crm-field mb-3" key={String(title)}>
              {String(title)}
              <textarea
                className="crm-input font-mono"
                rows={5}
                value={String(value)}
                onChange={(e) =>
                  (setter as (value: string) => void)(e.target.value)
                }
              />
            </label>
          ))}
        </details>
        <button className="crm-button" type="submit">
          Save draft
        </button>
      </fieldset>
      {error && (
        <p role="alert" className="text-red-500">
          {error}
        </p>
      )}
    </form>
  );
}

function JsonField({
  value,
  onChange,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const field = useRef<HTMLTextAreaElement>(null);
  const serialized = JSON.stringify(value);
  const [draft, setDraft] = useState({
    source: serialized,
    text: JSON.stringify(value, null, 2),
  });
  useEffect(() => {
    let error = "";
    try {
      JSON.parse(draft.text);
    } catch {
      error = "Enter valid JSON before saving.";
    }
    field.current?.setCustomValidity(error);
  }, [draft.text]);
  if (draft.source !== serialized) {
    setDraft({ source: serialized, text: JSON.stringify(value, null, 2) });
  }
  return (
    <textarea
      className="crm-input font-mono"
      rows={5}
      ref={field}
      value={draft.text}
      onChange={(e) => {
        const next = e.target.value;
        try {
          const parsed: unknown = JSON.parse(next);
          setDraft({ source: JSON.stringify(parsed), text: next });
          onChange(parsed);
          e.target.setCustomValidity("");
        } catch {
          setDraft({ source: serialized, text: next });
          e.target.setCustomValidity("Enter valid JSON before saving.");
        }
      }}
    />
  );
}
function Condition({
  value,
  onChange,
}: {
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
}) {
  return (
    <div className="space-y-3">
      <label className="crm-field">
        Field
        <input
          className="crm-input"
          value={String(value.field ?? "")}
          onChange={(e) => onChange({ ...value, field: e.target.value })}
          placeholder="lead.score"
        />
      </label>
      <label className="crm-field">
        Comparison
        <select
          className="crm-input"
          value={String(value.operator ?? "eq")}
          onChange={(e) => onChange({ ...value, operator: e.target.value })}
        >
          {[
            "eq",
            "ne",
            "contains",
            "not_contains",
            "starts_with",
            "ends_with",
            "gt",
            "lt",
            "gte",
            "lte",
            "empty",
            "not_empty",
            "exists",
            "changed",
            "changed_to",
            "changed_from",
          ].map((op) => (
            <option key={op}>{op}</option>
          ))}
        </select>
      </label>
      <label className="crm-field">
        Value
        <input
          className="crm-input"
          value={String(value.value ?? "")}
          onChange={(e) => {
            const next = e.target.value;
            onChange({
              ...value,
              value: ["gt", "lt", "gte", "lte"].includes(String(value.operator))
                ? Number(next)
                : next,
            });
          }}
        />
      </label>
      <details>
        <summary>AND / OR / NOT condition tree</summary>
        <JsonField
          value={value}
          onChange={(next) => onChange(next as Record<string, unknown>)}
        />
      </details>
    </div>
  );
}
