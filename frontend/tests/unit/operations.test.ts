import { test } from "node:test";
import assert from "node:assert/strict";
import {
  campaignStatus,
  validateWorkflow,
} from "../../src/services/operations";
import type { WorkflowInput } from "../../src/types/operations";

const workflow = (): WorkflowInput => ({
  name: "Follow up new leads",
  trigger: "lead.created",
  conditions: [],
  actions: [
    {
      tool: "create_task",
      arguments: { title: "Follow up", lead_id: "$event.id" },
    },
  ],
});
test("campaign display adapter maps backend sending without claiming delivery", () => {
  assert.equal(campaignStatus("sending"), "running");
  assert.equal(campaignStatus("scheduled"), "scheduled");
  assert.equal(campaignStatus("completed"), "completed");
});
test("workflow validation accepts a related task and preserves event references", () => {
  const input = workflow();
  assert.equal(validateWorkflow(input), null);
  assert.equal(input.actions[0].arguments.lead_id, "$event.id");
});
test("workflow validation rejects missing customer relations and empty updates", () => {
  const input = workflow();
  input.actions[0].arguments = { title: "Task" };
  assert.match(validateWorkflow(input)!, /customer relation/);
  input.actions = [
    { tool: "update_lead", arguments: { entity_id: "$event.id" } },
  ];
  assert.match(validateWorkflow(input)!, /changed field/);
});
test("workflow validation rejects invalid dates and fractional currency minor units", () => {
  const input = workflow();
  input.actions[0].arguments.due_date = "2026-99-01T00:00:00Z";
  assert.match(validateWorkflow(input)!, /valid ISO dates/);
  input.actions = [
    { tool: "update_deal", arguments: { entity_id: "$event.id", value: 1.5 } },
  ];
  assert.match(validateWorkflow(input)!, /whole currency minor units/);
});
test("workflow validation checks score bounds and required approved-action fields", () => {
  const input = workflow();
  input.conditions = [{ field: "ai_score", operator: "gt", value: 101 }];
  assert.match(validateWorkflow(input)!, /0 to 100/);
  input.conditions = [];
  input.actions = [
    {
      tool: "send_email",
      arguments: { conversation_id: "$event.id", body: "Hello" },
    },
  ];
  assert.match(validateWorkflow(input)!, /required fields/);
});
