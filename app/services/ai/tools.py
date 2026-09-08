"""AI tools can call approved CRM HTTP APIs only, using the caller's identity."""
from dataclasses import dataclass
from uuid import UUID
from app.core.rbac import get_role_permissions


@dataclass(frozen=True)
class ApprovedTool:
    permission: str
    method: str
    path: str


APPROVED_TOOLS = {
    "lead.read": ApprovedTool("leads:read", "GET", "/api/v1/leads"),
    "lead.create": ApprovedTool("leads:write", "POST", "/api/v1/leads"),
    "contact.read": ApprovedTool("contacts:read", "GET", "/api/v1/contacts"),
}
from app.services.crm.tools import PERMISSIONS as CRM_TOOL_PERMISSIONS
APPROVED_TOOLS.update({name: ApprovedTool(permission, "POST", "/api/v1/operations/tools/" + name)
                       for name, permission in CRM_TOOL_PERMISSIONS.items()})


class ToolPermissionLayer:
    def __init__(self, crm_http_client):
        self.client = crm_http_client

    async def execute(self, name, arguments, *, token, tenant_id, approved_tools, idempotency_key=None):
        # Verify against the CRM API each time; JWT role claims are not authoritative.
        if name not in APPROVED_TOOLS or name not in approved_tools:
            raise PermissionError("Tool not approved")
        from app.core.security import decode_token
        payload = decode_token(token)
        if not payload or payload.get("type") != "access" or payload.get("tenant_id") != str(UUID(str(tenant_id))):
            raise PermissionError("Invalid tool identity")
        if any(key in arguments for key in ("tenant_id", "user_id", "role", "permissions")):
            raise PermissionError("Tool identity override forbidden")
        spec = APPROVED_TOOLS[name]
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant_id)}
        if name in CRM_TOOL_PERMISSIONS:
            if not idempotency_key:
                raise ValueError("CRM tool invocation requires an idempotency key")
            headers["Idempotency-Key"] = idempotency_key
            arguments = {"arguments": arguments}
        response = await self.client.request(spec.method, spec.path, headers=headers,
                                              **({"params": arguments} if spec.method == "GET" else {"json": arguments}))
        response.raise_for_status()
        return response.json()
