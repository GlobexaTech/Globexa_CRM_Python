"""Apply the CRM's assigned-record boundary to alternate readers and tools.

Tenant RLS remains mandatory. This adds the narrower sales-executive scope,
including children linked to private leads, deals, tasks or conversations.
"""

from sqlalchemy import select, and_, or_, true, false
from app.models import Lead, Deal, Task, Conversation, Message, Membership, RoleEnum
from app.core.tenant_context import current_user


def _assigned(model, tenant_id, actor_id):
    clauses = []
    if model in (Lead, Deal, Task):
        clauses.append(model.owner_id == actor_id)
    for field, parent in (("lead_id", Lead), ("deal_id", Deal), ("task_id", Task)):
        if hasattr(model, field):
            column = getattr(model, field)
            clauses.append(
                or_(
                    column.is_(None),
                    column.in_(
                        select(parent.id).where(
                            parent.tenant_id == tenant_id, parent.owner_id == actor_id
                        )
                    ),
                )
            )
    if model is Message:
        clauses.append(
            Message.conversation_id.in_(
                select(Conversation.id).where(
                    Conversation.tenant_id == tenant_id,
                    _assigned(Conversation, tenant_id, actor_id),
                )
            )
        )
    return and_(*clauses) if clauses else true()


async def record_scope(db, model, tenant_id, actor_id=None):
    if model not in (Lead, Deal, Task, Message) and not any(
        hasattr(model, field) for field in ("lead_id", "deal_id", "task_id")
    ):
        # Non-record resources have their own permission checks. In particular,
        # revoked jobs must remain accessible to their failure finalizer.
        return true()
    actor_id = actor_id or db.info.get("security_context", (None, current_user.get()))[1]
    if actor_id is None:
        # Tenant-bound internal consumers have no interactive identity.
        return true()
    role = await db.scalar(
        select(Membership.role).where(
            Membership.tenant_id == tenant_id, Membership.user_id == actor_id
        )
    )
    if role is None:
        return false()
    return _assigned(model, tenant_id, actor_id) if role == RoleEnum.SALES_EXECUTIVE else true()
