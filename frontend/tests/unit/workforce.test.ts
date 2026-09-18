import { test } from "node:test";
import assert from "node:assert/strict";
import { allowedApiPath } from "../../src/auth/server/security";
import {
  approvalDecisionAllowed,
  approvalExplanation,
  executionActive,
  workforce,
} from "../../src/services/workforce";
import type { Approval } from "../../src/types/workforce";
import { api } from "../../src/api/client";

const request = (): Approval => ({
  id: "approval-id",
  agent_name: "sales",
  requesting_user_id: "requester",
  execution_id: null,
  action_type: "send_email",
  target: "customer@example.com",
  proposed_action: { body: "Approved text" },
  action_hash: "exact-stored-hash",
  status: "pending",
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 60000).toISOString(),
  decided_at: null,
  decided_by: null,
  rejection_reason: null,
  execution_result: null,
});
test("workforce proxy permits its route but rejects tenant overrides and traversal", () => {
  assert.equal(
    allowedApiPath(["workforce", "executions"]),
    "/api/v1/workforce/executions",
  );
  assert.throws(() => allowedApiPath(["workforce", "..", "auth"]));
  assert.throws(() =>
    allowedApiPath(["workforce", "approvals"], "tenant_id=other"),
  );
});
test("approval controls fail closed for own actions, expired requests and missing permission", () => {
  const approval = request();
  assert.equal(approvalDecisionAllowed(approval, "reviewer", true), true);
  assert.equal(approvalDecisionAllowed(approval, "requester", true), false);
  assert.equal(approvalDecisionAllowed(approval, "reviewer", false), false);
  assert.equal(
    approvalDecisionAllowed(
      { ...approval, status: "executed" },
      "reviewer",
      true,
    ),
    false,
  );
  assert.equal(
    approvalDecisionAllowed(
      { ...approval, expires_at: new Date(Date.now() - 1000).toISOString() },
      "reviewer",
      true,
    ),
    false,
  );
});
test("approval decisions transmit only the exact stored hash and reviewer decision", async () => {
  const original = api.post;
  let submitted: unknown;
  try {
    api.post = (async (path: string, body: unknown) => {
      submitted = { path, body };
      return request();
    }) as typeof api.post;
    await workforce.decide(
      request(),
      "approved",
      "Reviewed recipient and content",
    );
    assert.deepEqual(submitted, {
      path: "/workforce/approvals/approval-id/decision",
      body: {
        decision: "approved",
        action_hash: "exact-stored-hash",
        reason: "Reviewed recipient and content",
      },
    });
  } finally {
    api.post = original;
  }
});
test("display distinguishes approval from execution and sent from delivery", () => {
  assert.match(approvalExplanation("approved"), /not yet been confirmed/);
  assert.match(approvalExplanation("executed"), /provider state for delivery/);
  assert.equal(executionActive("queued"), true);
  assert.equal(executionActive("running"), true);
  assert.equal(executionActive("failed"), false);
  assert.equal(executionActive("completed"), false);
});
