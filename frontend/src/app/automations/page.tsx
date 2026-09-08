"use client";
import { useState } from "react";
import { Plus, Zap } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import { Dialog } from "@/components/Dialog";
import { JobStatus } from "@/components/JobStatus";
import { ResourceState } from "@/components/ResourceState";
import { useConfirm } from "@/components/ConfirmProvider";
import { useSession } from "@/auth/SessionProvider";
import { useResource } from "@/hooks/useResource";
import { useAction } from "@/hooks/useAction";
import { operations, validateWorkflow } from "@/services/operations";
import {
  aiCapabilities,
  workflowTools,
  workflowTriggers,
} from "@/types/operations";
import type {
  Execution,
  Page,
  Workflow,
  WorkflowAction,
  WorkflowCondition,
  WorkflowDetail,
  WorkflowInput,
  WorkflowTool,
} from "@/types/operations";

const actionFields: Record<WorkflowTool, string[]> = {
  create_task: [
    "title",
    "description",
    "lead_id",
    "deal_id",
    "contact_id",
    "company_id",
    "due_date",
    "priority",
    "owner_id",
  ],
  update_lead: ["entity_id", "title", "description", "status"],
  update_deal: ["entity_id", "title", "description", "stage_id", "value"],
  add_note: ["content", "lead_id", "deal_id", "contact_id", "company_id"],
  send_email: ["conversation_id", "recipient", "body"],
  assign_owner: ["entity_id", "owner_id"],
  invoke_ai: ["capability", "entity_id"],
};
const requiredFields: Record<WorkflowTool, string[]> = {
  create_task: ["title"],
  update_lead: ["entity_id"],
  update_deal: ["entity_id"],
  add_note: ["content"],
  send_email: ["conversation_id", "recipient", "body"],
  assign_owner: ["entity_id", "owner_id"],
  invoke_ai: ["capability", "entity_id"],
};
const idPattern =
  "([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\\$event\\.(id|contact_id|company_id|lead_id|deal_id|stage_id|owner_id))";
export default function AutomationsPage() {
  const { session, can } = useSession();
  return (
    <WorkflowWorkspace
      key={`${session?.tenant_id}:${session?.version}`}
      can={can}
    />
  );
}
function WorkflowWorkspace({ can }: { can: (permission: string) => boolean }) {
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [create, setCreate] = useState(false);
  const [enabled, setEnabled] = useState("");
  const list = useResource<Page<Workflow>>(
    `/operations/workflows?limit=20&offset=${offset}${enabled ? `&enabled=${enabled}` : ""}`,
    can("automation:read"),
  );
  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />
      <section className="min-w-0 flex-1 p-4 sm:p-8">
        <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue)]">
              GLOBEXA CRM
            </p>
            <h1 className="mt-2 text-3xl font-semibold">Automations</h1>
            <p className="crm-muted">
              Event-driven workflows with approved actions
            </p>
          </div>
          {can("automation:write") && (
            <button className="crm-button" onClick={() => setCreate(true)}>
              <Plus size={16} />
              New workflow
            </button>
          )}
        </header>
        {!can("automation:read") ? (
          <p role="alert">Your role cannot read workflows.</p>
        ) : (
          <>
            <div className="card mb-4 flex flex-wrap items-end gap-3 p-4">
              <label className="crm-field">
                Workflow state
                <select
                  className="crm-input"
                  value={enabled}
                  onChange={(e) => {
                    setEnabled(e.target.value);
                    setOffset(0);
                  }}
                >
                  <option value="">All workflows</option>
                  <option value="true">Enabled</option>
                  <option value="false">Disabled</option>
                </select>
              </label>
              <button
                className="crm-secondary"
                onClick={() => void list.refetch()}
              >
                Refresh workflows
              </button>
            </div>
            <ResourceState
              loading={list.isLoading}
              error={list.error}
              empty={list.data?.items.length === 0}
              onRetry={() => void list.refetch()}
            >
              <div className="grid gap-4 xl:grid-cols-2">
                {list.data?.items.map((workflow) => (
                  <article key={workflow.id} className="card p-5">
                    <div className="flex items-start gap-3">
                      <Zap className="mt-1 shrink-0 text-[var(--blue)]" />
                      <div>
                        <h2 className="text-lg font-semibold">
                          {workflow.name}
                        </h2>
                        <p className="crm-muted">
                          {workflow.enabled ? "Enabled" : "Disabled"} · Version{" "}
                          {workflow.version}
                        </p>
                      </div>
                    </div>
                    <button
                      className="crm-secondary mt-4"
                      onClick={() => setSelected(workflow.id)}
                    >
                      Definition and execution history
                    </button>
                  </article>
                ))}
              </div>
            </ResourceState>
            <nav className="crm-actions mt-5" aria-label="Workflow pages">
              <button
                className="crm-secondary"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 20))}
              >
                Previous
              </button>
              <button
                className="crm-secondary"
                disabled={!list.data || offset + 20 >= list.data.total}
                onClick={() => setOffset(offset + 20)}
              >
                Next
              </button>
            </nav>
          </>
        )}
        <Dialog
          open={create}
          title="Create workflow"
          onClose={() => setCreate(false)}
        >
          {create && (
            <WorkflowEditor
              onSaved={(id) => {
                setCreate(false);
                setSelected(id);
              }}
            />
          )}
        </Dialog>
        <Dialog
          open={!!selected}
          title="Workflow details"
          onClose={() => setSelected("")}
        >
          {selected && (
            <WorkflowView
              key={selected}
              id={selected}
              writable={can("automation:write")}
            />
          )}
        </Dialog>
      </section>
    </main>
  );
}
function WorkflowView({ id, writable }: { id: string; writable: boolean }) {
  const detail = useResource<WorkflowDetail>(`/operations/workflows/${id}`);
  const [offset, setOffset] = useState(0);
  const executions = useResource<Page<Execution>>(
    `/operations/workflows/${id}/executions?limit=20&offset=${offset}`,
  );
  const [edit, setEdit] = useState(false);
  const action = useAction();
  const { confirm } = useConfirm();
  return (
    <div className="space-y-5">
      <ResourceState
        loading={detail.isLoading}
        error={detail.error}
        onRetry={() => void detail.refetch()}
      >
        {detail.data && (
          <>
            <h2 className="text-xl font-semibold">
              {detail.data.definition?.name || "Legacy workflow"}
            </h2>
            <p>
              {detail.data.enabled ? "Enabled" : "Disabled"} · Version{" "}
              {detail.data.version}
            </p>
            <div className="crm-actions">
              <button
                className="crm-secondary"
                onClick={() => {
                  void detail.refetch();
                  void executions.refetch();
                }}
              >
                Refresh workflow
              </button>
              {writable && (
                <>
                  <button
                    className="crm-secondary"
                    onClick={() => setEdit(!edit)}
                  >
                    Edit definition
                  </button>
                  <button
                    className={
                      detail.data.enabled ? "crm-danger" : "crm-button"
                    }
                    disabled={action.pending || !detail.data.definition}
                    onClick={() =>
                      void (async () => {
                        const enabled = !detail.data!.enabled;
                        if (
                          !enabled &&
                          !(await confirm({
                            title: "Disable workflow?",
                            message:
                              "Future execution and pending actions will be rejected while this workflow is disabled.",
                            tone: "warning",
                            confirmText: "Disable workflow",
                          }))
                        )
                          return;
                        await action.run(() =>
                          operations.toggleWorkflow(id, enabled),
                        );
                      })()
                    }
                  >
                    {detail.data.enabled
                      ? "Disable workflow"
                      : "Enable workflow"}
                  </button>
                </>
              )}
            </div>
            {edit && (
              <WorkflowEditor
                id={id}
                initial={detail.data.definition || undefined}
                onSaved={() => setEdit(false)}
              />
            )}
            {!edit && detail.data.definition && (
              <div className="space-y-3 rounded-xl bg-[var(--panel2)] p-4">
                <p className="text-sm">
                  <strong>Trigger:</strong> {detail.data.definition.trigger}
                </p>
                <h3 className="font-semibold">Conditions</h3>
                {detail.data.definition.conditions.length ? (
                  <ul className="text-sm">
                    {detail.data.definition.conditions.map(
                      (condition, index) => (
                        <li key={index}>
                          {condition.field} {condition.operator}{" "}
                          {String(condition.value)}
                        </li>
                      ),
                    )}
                  </ul>
                ) : (
                  <p className="text-sm">
                    All events of the selected trigger type
                  </p>
                )}
                <h3 className="font-semibold">Approved actions</h3>
                <ol className="list-inside list-decimal space-y-3 text-sm">
                  {detail.data.definition.actions.map((item, index) => (
                    <li key={index}>
                      <strong>{item.tool.replaceAll("_", " ")}</strong>
                      <dl className="mt-1 space-y-1">
                        {Object.entries(item.arguments).map(([key, value]) => (
                          <div key={key}>
                            <dt className="inline font-medium">{key}: </dt>
                            <dd className="inline break-words whitespace-pre-wrap">
                              {String(value)}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            <p className="crm-muted">
              Saving a definition creates a new version and disables the
              workflow. Enable it after review. Execution requires the owner’s
              current permissions and automation entitlement.
            </p>
          </>
        )}
      </ResourceState>
      {action.error && (
        <p role="alert" className="crm-error">
          {action.error}
        </p>
      )}
      <section>
        <h3 className="mb-3 font-semibold">Execution history</h3>
        <ResourceState
          loading={executions.isLoading}
          error={executions.error}
          empty={executions.data?.items.length === 0}
          onRetry={() => void executions.refetch()}
        >
          <ul className="space-y-3">
            {executions.data?.items.map((log) => (
              <li
                key={log.id}
                className="rounded-xl border border-[var(--border)] p-3"
              >
                <p>
                  <strong>{log.status}</strong> · Version {log.version} ·{" "}
                  {log.attempts} attempt(s)
                </p>
                <p className="break-all text-xs">Event: {log.event_id}</p>
                <p className="break-all text-xs">Execution: {log.id}</p>
                {log.error_code && (
                  <p role="alert" className="crm-error">
                    {log.error_code}
                  </p>
                )}
                {log.job_id && writable && (
                  <JobStatus
                    jobId={log.job_id}
                    onComplete={() => void executions.refetch()}
                  />
                )}
                {log.status === "failed" && !log.job_id && (
                  <p className="crm-muted">
                    This execution has no linked retryable job.
                  </p>
                )}
              </li>
            ))}
          </ul>
        </ResourceState>
        <nav className="crm-actions mt-3" aria-label="Execution pages">
          <button
            className="crm-secondary"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 20))}
          >
            Previous executions
          </button>
          <button
            className="crm-secondary"
            disabled={!executions.data || offset + 20 >= executions.data.total}
            onClick={() => setOffset(offset + 20)}
          >
            Next executions
          </button>
        </nav>
      </section>
    </div>
  );
}
function WorkflowEditor({
  initial,
  id,
  onSaved,
}: {
  initial?: WorkflowInput;
  id?: string;
  onSaved: (id: string) => void;
}) {
  const [name, setName] = useState(initial?.name || "");
  const [trigger, setTrigger] = useState<WorkflowInput["trigger"]>(
    initial?.trigger || "lead.created",
  );
  const [conditions, setConditions] = useState<WorkflowCondition[]>(
    initial?.conditions || [],
  );
  const [actions, setActions] = useState<WorkflowAction[]>(
    initial?.actions || [
      { tool: "create_task", arguments: { title: "", lead_id: "$event.id" } },
    ],
  );
  const [validation, setValidation] = useState("");
  const action = useAction();
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setValidation("");
    for (const item of actions) {
      if (
        ["create_task", "add_note"].includes(item.tool) &&
        !["lead_id", "deal_id", "contact_id", "company_id"].some(
          (field) => item.arguments[field],
        )
      ) {
        setValidation(
          "Each task or note action needs a lead, contact, company or deal relation.",
        );
        return;
      }
      if (
        ["update_lead", "update_deal"].includes(item.tool) &&
        Object.keys(item.arguments).filter(
          (field) => field !== "entity_id" && item.arguments[field] !== "",
        ).length === 0
      ) {
        setValidation("An update action needs at least one changed field.");
        return;
      }
    }
    const body: WorkflowInput = {
      name: name.trim(),
      trigger,
      conditions,
      actions: actions.map((item) => ({
        ...item,
        arguments: Object.fromEntries(
          Object.entries(item.arguments).filter(([, value]) => value !== ""),
        ),
      })),
    };
    const error = validateWorkflow(body);
    if (error) {
      setValidation(error);
      return;
    }
    await action.run(async () => {
      const result = await operations.saveWorkflow(body, id);
      onSaved(result.id);
      return result;
    });
  }
  function argument(index: number, field: string, value: string | number) {
    setActions(
      actions.map((item, i) =>
        i === index
          ? { ...item, arguments: { ...item.arguments, [field]: value } }
          : item,
      ),
    );
  }
  return (
    <form className="crm-form" onSubmit={submit}>
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
        Trigger
        <select
          className="crm-input"
          value={trigger}
          onChange={(e) =>
            setTrigger(e.target.value as WorkflowInput["trigger"])
          }
        >
          {workflowTriggers.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </label>
      <h3 className="font-semibold">Conditions</h3>
      {conditions.map((condition, index) => (
        <fieldset
          className="grid gap-3 rounded-xl border border-[var(--border)] p-3 sm:grid-cols-2"
          key={index}
        >
          <legend>Condition {index + 1}</legend>
          <label className="crm-field">
            Field
            <select
              className="crm-input"
              value={condition.field}
              onChange={(e) =>
                setConditions(
                  conditions.map((item, i) =>
                    i === index
                      ? {
                          ...item,
                          field: e.target.value as WorkflowCondition["field"],
                          value: ["ai_score", "value"].includes(e.target.value)
                            ? 0
                            : "",
                          operator: "eq",
                        }
                      : item,
                  ),
                )
              }
            >
              {[
                "status",
                "stage_id",
                "ai_score",
                "value",
                "source",
                "direction",
              ].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label className="crm-field">
            Operator
            <select
              className="crm-input"
              value={condition.operator}
              onChange={(e) =>
                setConditions(
                  conditions.map((item, i) =>
                    i === index
                      ? {
                          ...item,
                          operator: e.target
                            .value as WorkflowCondition["operator"],
                        }
                      : item,
                  ),
                )
              }
            >
              {(typeof condition.value === "number"
                ? ["eq", "ne", "gt", "lt"]
                : ["eq", "ne"]
              ).map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label className="crm-field">
            Comparison value
            <input
              className="crm-input"
              required
              type={typeof condition.value === "number" ? "number" : "text"}
              value={String(condition.value ?? "")}
              onChange={(e) =>
                setConditions(
                  conditions.map((item, i) =>
                    i === index
                      ? {
                          ...item,
                          value:
                            typeof item.value === "number"
                              ? Number(e.target.value)
                              : e.target.value,
                        }
                      : item,
                  ),
                )
              }
            />
          </label>
          <button
            type="button"
            className="crm-secondary self-end"
            onClick={() =>
              setConditions(conditions.filter((_, i) => i !== index))
            }
          >
            Remove condition {index + 1}
          </button>
        </fieldset>
      ))}
      <button
        type="button"
        className="crm-secondary"
        disabled={conditions.length >= 20}
        onClick={() =>
          setConditions([
            ...conditions,
            { field: "status", operator: "eq", value: "" },
          ])
        }
      >
        Add condition
      </button>
      <h3 className="font-semibold">Approved actions</h3>
      <p className="crm-muted">
        Resource references accept a backend UUID or a listed event reference.
        $event.id means the record that triggered this workflow; choose the
        corresponding relation field. Action values are structured data and
        never executable code.
      </p>
      <datalist id="event-references">
        {[
          "id",
          "lead_id",
          "contact_id",
          "company_id",
          "deal_id",
          "stage_id",
          "owner_id",
        ].map((value) => (
          <option key={value} value={`$event.${value}`} />
        ))}
      </datalist>
      {actions.map((item, index) => (
        <fieldset
          key={index}
          className="space-y-3 rounded-xl border border-[var(--border)] p-3"
        >
          <legend>Action {index + 1}</legend>
          <label className="crm-field">
            Action type
            <select
              className="crm-input"
              value={item.tool}
              onChange={(e) =>
                setActions(
                  actions.map((value, i) =>
                    i === index
                      ? { tool: e.target.value as WorkflowTool, arguments: {} }
                      : value,
                  ),
                )
              }
            >
              {workflowTools.map((value) => (
                <option key={value} value={value}>
                  {value.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          {actionFields[item.tool].map((field) => (
            <label key={field} className="crm-field">
              {field.replaceAll("_", " ")}
              {requiredFields[item.tool].includes(field) ? " (required)" : ""}
              {field === "capability" ? (
                <select
                  className="crm-input"
                  required
                  value={item.arguments[field] || ""}
                  onChange={(e) => argument(index, field, e.target.value)}
                >
                  <option value="">Choose controlled capability</option>
                  {aiCapabilities.map((capability) => (
                    <option key={capability.value} value={capability.value}>
                      {capability.label}
                    </option>
                  ))}
                </select>
              ) : field === "status" || field === "priority" ? (
                <select
                  className="crm-input"
                  value={item.arguments[field] || ""}
                  onChange={(e) => argument(index, field, e.target.value)}
                >
                  <option value="">No change</option>
                  {(field === "priority"
                    ? ["low", "medium", "high", "urgent"]
                    : [
                        "new",
                        "contacted",
                        "qualified",
                        "unqualified",
                        "nurturing",
                        "converted",
                        "lost",
                      ]
                  ).map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              ) : ["body", "content", "description"].includes(field) ? (
                <textarea
                  className="crm-input"
                  required={requiredFields[item.tool].includes(field)}
                  maxLength={10000}
                  value={item.arguments[field] || ""}
                  onChange={(e) => argument(index, field, e.target.value)}
                />
              ) : (
                <input
                  className="crm-input"
                  required={requiredFields[item.tool].includes(field)}
                  type={
                    field === "value"
                      ? "number"
                      : field === "recipient"
                        ? "email"
                        : "text"
                  }
                  min={field === "value" ? 0 : undefined}
                  step={field === "value" ? 1 : undefined}
                  pattern={
                    field.endsWith("_id")
                      ? idPattern
                      : field === "due_date"
                        ? "\d{4}-\d{2}-\d{2}T.+"
                        : undefined
                  }
                  title={
                    field.endsWith("_id")
                      ? "Enter a UUID or listed $event reference"
                      : field === "due_date"
                        ? "ISO date with timezone, for example 2026-10-01T09:00:00Z"
                        : undefined
                  }
                  list={field.endsWith("_id") ? "event-references" : undefined}
                  value={item.arguments[field] ?? ""}
                  onChange={(e) =>
                    argument(
                      index,
                      field,
                      field === "value" && e.target.value !== ""
                        ? Number(e.target.value)
                        : e.target.value,
                    )
                  }
                />
              )}
            </label>
          ))}
          <button
            type="button"
            className="crm-secondary"
            disabled={actions.length === 1}
            onClick={() => setActions(actions.filter((_, i) => i !== index))}
          >
            Remove action {index + 1}
          </button>
        </fieldset>
      ))}
      <button
        type="button"
        className="crm-secondary"
        disabled={actions.length >= 10}
        onClick={() =>
          setActions([...actions, { tool: "create_task", arguments: {} }])
        }
      >
        Add approved action
      </button>
      {(validation || action.error) && (
        <p role="alert" className="crm-error">
          {validation || action.error}
        </p>
      )}
      <button className="crm-button" disabled={action.pending}>
        {action.pending ? "Saving…" : "Save disabled workflow"}
      </button>
    </form>
  );
}
