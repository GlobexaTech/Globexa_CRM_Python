"""
In-CRM AI Assistant Service for Globexa CRM.
ChatGPT-style assistant with controlled tool calling for CRM actions.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Callable
from uuid import UUID
from datetime import datetime, timezone
import structlog
import json
import inspect

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import Lead, Contact, Company, Deal, Campaign, Task, User, Membership, RoleEnum
from app.services.ai.router import get_ai_router, AITaskTypeEnum

logger = structlog.get_logger()


@dataclass
class ToolDefinition:
    """Tool definition for AI assistant."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    required_permissions: List[str]
    handler: Callable


@dataclass
class ToolCall:
    """Tool call from AI."""
    name: str
    arguments: Dict[str, Any]
    call_id: str


@dataclass
class ToolResult:
    """Tool execution result."""
    call_id: str
    name: str
    result: Any
    error: Optional[str] = None


@dataclass
class AssistantMessage:
    """Assistant conversation message."""
    role: str  # user, assistant, tool
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


@dataclass
class AssistantResponse:
    """Assistant response."""
    message: str
    tool_calls: Optional[List[ToolCall]] = None
    tool_results: Optional[List[ToolResult]] = None


class AIAssistantService:
    """
    In-CRM AI Assistant with controlled tool calling.
    
    The assistant never gets unrestricted database access.
    Instead, it uses a controlled tool layer with permission checks.
    """

    def __init__(self):
        self.router = get_ai_router()
        self.tools = self._register_tools()

    def _register_tools(self) -> Dict[str, ToolDefinition]:
        """Register all available tools."""
        return {
            "search_leads": ToolDefinition(
                name="search_leads",
                description="Search for leads with filters",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query (name, company, email)"},
                        "status": {"type": "string", "enum": ["new", "contacted", "qualified", "nurturing", "converted", "lost"]},
                        "owner_id": {"type": "string", "description": "Filter by owner"},
                        "min_score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "limit": {"type": "integer", "default": 20, "maximum": 100},
                    },
                    "required": [],
                },
                required_permissions=["ai:read_leads", "leads:read"],
                handler=self._search_leads,
            ),
            "get_lead": ToolDefinition(
                name="get_lead",
                description="Get detailed lead information",
                parameters={
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string", "description": "Lead UUID"},
                    },
                    "required": ["lead_id"],
                },
                required_permissions=["ai:read_leads", "leads:read"],
                handler=self._get_lead,
            ),
            "create_campaign": ToolDefinition(
                name="create_campaign",
                description="Create a new email campaign",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string", "enum": ["broadcast", "sequence", "triggered"]},
                        "subject": {"type": "string"},
                        "html_content": {"type": "string"},
                        "audience_type": {"type": "string", "enum": ["static", "dynamic"]},
                        "contact_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "type", "subject", "html_content"],
                },
                required_permissions=["ai:draft_email", "campaigns:write"],
                handler=self._create_campaign,
            ),
            "assign_lead": ToolDefinition(
                name="assign_lead",
                description="Assign a lead to a salesperson",
                parameters={
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string"},
                        "owner_id": {"type": "string"},
                    },
                    "required": ["lead_id", "owner_id"],
                },
                required_permissions=["ai:assign_leads", "leads:assign"],
                handler=self._assign_lead,
            ),
            "schedule_followup": ToolDefinition(
                name="schedule_followup",
                description="Schedule a follow-up task",
                parameters={
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string"},
                        "title": {"type": "string"},
                        "due_date": {"type": "string", "format": "date-time"},
                        "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                    },
                    "required": ["lead_id", "title", "due_date"],
                },
                required_permissions=["ai:draft_email", "tasks:write"],
                handler=self._schedule_followup,
            ),
            "send_email": ToolDefinition(
                name="send_email",
                description="Send an email to a contact",
                parameters={
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                        "template_id": {"type": "string"},
                    },
                    "required": ["lead_id", "subject", "body"],
                },
                required_permissions=["ai:send_email", "campaigns:send"],
                handler=self._send_email,
            ),
            "create_proposal": ToolDefinition(
                name="create_proposal",
                description="Generate a proposal for a deal",
                parameters={
                    "type": "object",
                    "properties": {
                        "deal_id": {"type": "string"},
                        "template_id": {"type": "string"},
                    },
                    "required": ["deal_id"],
                },
                required_permissions=["ai:create_proposal", "deals:write"],
                handler=self._create_proposal,
            ),
            "update_stage": ToolDefinition(
                name="update_stage",
                description="Update deal pipeline stage",
                parameters={
                    "type": "object",
                    "properties": {
                        "deal_id": {"type": "string"},
                        "stage_id": {"type": "string"},
                    },
                    "required": ["deal_id", "stage_id"],
                },
                required_permissions=["ai:change_stage", "deals:write"],
                handler=self._update_stage,
            ),
            "search_contacts": ToolDefinition(
                name="search_contacts",
                description="Search for contacts",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "company_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": [],
                },
                required_permissions=["contacts:read"],
                handler=self._search_contacts,
            ),
            "get_deal": ToolDefinition(
                name="get_deal",
                description="Get detailed deal information",
                parameters={
                    "type": "object",
                    "properties": {
                        "deal_id": {"type": "string"},
                    },
                    "required": ["deal_id"],
                },
                required_permissions=["deals:read"],
                handler=self._get_deal,
            ),
            "search_companies": ToolDefinition(
                name="search_companies",
                description="Search for companies",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "industry": {"type": "string"},
                        "size": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": [],
                },
                required_permissions=["companies:read"],
                handler=self._search_companies,
            ),
        }

    async def chat(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        message: str,
        conversation_history: Optional[List[AssistantMessage]] = None,
        correlation_id: Optional[str] = None,
    ) -> AssistantResponse:
        """
        Process a chat message from the user.
        
        Flow:
        1. Build context with user permissions and tenant info
        2. Call AI with tools enabled
        3. If AI calls tools, execute them with permission checks
        4. Return results to AI for final response
        5. Return final response to user
        """
        # Get user permissions
        user_permissions = await self._get_user_permissions(db, user_id, tenant_id)
        
        # Filter tools by permissions
        available_tools = {
            name: tool for name, tool in self.tools.items()
            if all(p in user_permissions for p in tool.required_permissions)
        }

        # Build system prompt
        system_prompt = self._build_system_prompt(available_tools, tenant_id, user_id)

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        
        if conversation_history:
            for msg in conversation_history[-10:]:  # Last 10 messages
                if msg.role == "user":
                    messages.append({"role": "user", "content": msg.content})
                elif msg.role == "assistant":
                    messages.append({"role": "assistant", "content": msg.content})
                elif msg.role == "tool":
                    messages.append({
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    })

        messages.append({"role": "user", "content": message})

        # Convert tools to OpenAI format
        openai_tools = []
        for tool in available_tools.values():
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })

        # First AI call
        result = await self.router.complete(
            task_type=AITaskTypeEnum.CHAT_ASSISTANT,
            prompt=message,
            tenant_id=tenant_id,
            user_id=user_id,
            correlation_id=correlation_id,
            system_prompt=system_prompt,
            tools=openai_tools,
            tool_choice="auto",
            temperature=0.3,
            db=db,
        )

        if not result.success or not result.tool_calls:
            return AssistantResponse(
                message=result.content or "I apologize, but I couldn't process that request.",
                tool_calls=None,
                tool_results=None,
            )

        # Execute tool calls
        tool_results = []
        for tool_call in result.tool_calls:
            tool_result = await self._execute_tool(
                db, tenant_id, user_id, user_permissions,
                tool_call, correlation_id
            )
            tool_results.append(tool_result)

        # Second AI call with tool results
        tool_messages = []
        for tr in tool_results:
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tr.call_id,
                "content": json.dumps(tr.result) if not tr.error else f"Error: {tr.error}",
            })

        # Get final response
        final_result = await self.router.complete(
            task_type=AITaskTypeEnum.CHAT_ASSISTANT,
            prompt="",  # Empty - context in messages
            tenant_id=tenant_id,
            user_id=user_id,
            correlation_id=correlation_id,
            system_prompt=system_prompt,
            tools=openai_tools,
            tool_choice="none",
            temperature=0.3,
            db=db,
        )

        return AssistantResponse(
            message=final_result.content or "Task completed.",
            tool_calls=result.tool_calls,
            tool_results=tool_results,
        )

    def _build_system_prompt(
        self,
        available_tools: Dict[str, ToolDefinition],
        tenant_id: UUID,
        user_id: UUID,
    ) -> str:
        """Build system prompt with available tools."""
        tool_descriptions = "\n".join([
            f"- {name}: {tool.description}"
            for name, tool in available_tools.items()
        ])

        return f"""You are Globexa AI Assistant, an AI-powered sales assistant inside the Globexa CRM.

You help sales teams by:
- Finding and analyzing leads, contacts, companies, and deals
- Creating and managing campaigns
- Assigning leads and scheduling follow-ups
- Generating proposals and updating deal stages
- Answering questions about CRM data

Available tools:
{tool_descriptions}

Rules:
1. Always use tools to access CRM data - never guess or hallucinate
2. Ask for clarification if user request is ambiguous
3. Explain what you're doing and why
4. Respect user permissions - only use tools you have access to
5. Be concise but thorough
6. If a tool fails, explain the error and suggest alternatives

Current context:
- Tenant: {tenant_id}
- User: {user_id}
- You have access to {len(available_tools)} tools based on your permissions.
"""

    async def _get_user_permissions(
        self,
        db: AsyncSession,
        user_id: UUID,
        tenant_id: UUID,
    ) -> List[str]:
        """Get all permissions for user in tenant."""
        # Get membership
        result = await db.execute(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.tenant_id == tenant_id,
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            return []

        # Get role permissions
        from app.api.deps import get_role_permissions
        return list(get_role_permissions(membership.role))

    async def _execute_tool(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        user_permissions: List[str],
        tool_call: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> ToolResult:
        """Execute a tool call with permission checks."""
        call_id = tool_call.get("id", "unknown")
        name = tool_call.get("function", {}).get("name", "unknown")
        arguments = tool_call.get("function", {}).get("arguments", {})
        
        if isinstance(arguments, str):
            arguments = json.loads(arguments)

        tool = self.tools.get(name)
        if not tool:
            return ToolResult(
                call_id=call_id,
                name=name,
                result=None,
                error=f"Unknown tool: {name}",
            )

        # Check permissions
        if not all(p in user_permissions for p in tool.required_permissions):
            return ToolResult(
                call_id=call_id,
                name=name,
                result=None,
                error=f"Permission denied. Required: {tool.required_permissions}",
            )

        try:
            # Execute handler
            result = await tool.handler(db, tenant_id, user_id, arguments, correlation_id)
            return ToolResult(
                call_id=call_id,
                name=name,
                result=result,
            )
        except Exception as e:
            logger.error("Tool execution failed", tool=name, error=str(e))
            return ToolResult(
                call_id=call_id,
                name=name,
                result=None,
                error=str(e),
            )

    # =========================================================================
    # Tool Handlers
    # =========================================================================

    async def _search_leads(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        args: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        query = select(Lead).where(Lead.tenant_id == tenant_id).options(
            selectinload(Lead.contact).selectinload(Contact.company),
            selectinload(Lead.owner),
        )

        if args.get("query"):
            search = f"%{args['query']}%"
            query = query.where(
                or_(
                    Lead.title.ilike(search),
                    Lead.contact.has(Contact.first_name.ilike(search)),
                    Lead.contact.has(Contact.last_name.ilike(search)),
                    Lead.contact.has(Contact.email.ilike(search)),
                    Lead.company.has(Company.name.ilike(search)),
                )
            )

        if args.get("status"):
            query = query.where(Lead.status == args["status"])

        if args.get("owner_id"):
            query = query.where(Lead.owner_id == UUID(args["owner_id"]))

        if args.get("min_score"):
            query = query.where(Lead.ai_score >= args["min_score"])

        limit = min(args.get("limit", 20), 100)
        query = query.order_by(Lead.ai_score.desc().nullslast(), Lead.created_at.desc()).limit(limit)

        result = await db.execute(query)
        leads = result.scalars().all()

        return {
            "leads": [
                {
                    "id": str(l.id),
                    "title": l.title,
                    "status": l.status.value,
                    "ai_score": l.ai_score,
                    "contact": l.contact.full_name if l.contact else None,
                    "company": l.company.name if l.company else None,
                    "owner": l.owner.full_name if l.owner else None,
                }
                for l in leads
            ],
            "count": len(leads),
        }

    async def _get_lead(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        args: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        lead_id = UUID(args["lead_id"])
        
        result = await db.execute(
            select(Lead)
            .where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
            .options(
                selectinload(Lead.contact).selectinload(Contact.company),
                selectinload(Lead.company),
                selectinload(Lead.owner),
                selectinload(Lead.activities).limit(10),
            )
        )
        lead = result.scalar_one_or_none()
        
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        return {
            "id": str(lead.id),
            "title": lead.title,
            "description": lead.description,
            "status": lead.status.value,
            "ai_score": lead.ai_score,
            "ai_score_reason": lead.ai_score_reason,
            "ai_next_action": lead.ai_next_action,
            "contact": {
                "id": str(lead.contact.id) if lead.contact else None,
                "name": lead.contact.full_name if lead.contact else None,
                "email": lead.contact.email if lead.contact else None,
                "title": lead.contact.title if lead.contact else None,
            } if lead.contact else None,
            "company": {
                "id": str(lead.company.id) if lead.company else None,
                "name": lead.company.name if lead.company else None,
                "industry": lead.company.industry if lead.company else None,
                "size": lead.company.size if lead.company else None,
            } if lead.company else None,
            "owner": {
                "id": str(lead.owner.id) if lead.owner else None,
                "name": lead.owner.full_name if lead.owner else None,
            } if lead.owner else None,
            "activities": [
                {
                    "type": a.type.value,
                    "subject": a.subject,
                    "description": a.description,
                    "created_at": a.created_at.isoformat(),
                }
                for a in lead.activities[:10]
            ],
        }

    async def _create_campaign(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        args: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        from app.models import Campaign, CampaignAudience, CampaignTemplate, CampaignTypeEnum
        
        campaign = Campaign(
            tenant_id=tenant_id,
            name=args["name"],
            type=CampaignTypeEnum(args["type"]),
            sender_name="Sales Team",
            sender_email="sales@example.com",
            created_by_id=user_id,
        )
        db.add(campaign)
        await db.flush()

        # Create template
        template = CampaignTemplate(
            tenant_id=tenant_id,
            campaign_id=campaign.id,
            step_order=0,
            name="Main Template",
            subject=args["subject"],
            html_content=args["html_content"],
        )
        db.add(template)

        # Create audience if contact_ids provided
        if args.get("contact_ids"):
            audience = CampaignAudience(
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                type="static" if args.get("audience_type") != "dynamic" else "dynamic",
                name=f"{campaign.name} Audience",
                contact_ids=[UUID(cid) for cid in args["contact_ids"]],
            )
            db.add(audience)

        await db.commit()

        return {"id": str(campaign.id), "message": "Campaign created"}

    async def _assign_lead(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        args: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        lead_id = UUID(args["lead_id"])
        owner_id = UUID(args["owner_id"])

        result = await db.execute(
            select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
        )
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Verify owner exists in tenant
        result = await db.execute(
            select(Membership).where(
                Membership.user_id == owner_id,
                Membership.tenant_id == tenant_id,
                Membership.role.in_([RoleEnum.SALES_EXECUTIVE, RoleEnum.SALES_MANAGER]),
            )
        )
        if not result.scalar_one_or_none():
            raise ValueError(f"User {owner_id} not eligible for lead assignment")

        lead.owner_id = owner_id
        lead.assigned_by_id = user_id
        lead.assigned_at = datetime.now(timezone.utc)
        await db.commit()

        return {"message": f"Lead assigned to {owner_id}"}

    async def _schedule_followup(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        args: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        from app.models import Task, TaskPriorityEnum
        
        lead_id = UUID(args["lead_id"])
        due_date = datetime.fromisoformat(args["due_date"].replace("Z", "+00:00"))

        task = Task(
            tenant_id=tenant_id,
            lead_id=lead_id,
            title=args["title"],
            due_date=due_date,
            priority=TaskPriorityEnum(args.get("priority", "medium")),
            owner_id=user_id,
            created_by_id=user_id,
        )
        db.add(task)
        await db.commit()

        return {"id": str(task.id), "message": "Follow-up scheduled"}

    async def _send_email(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        args: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        # This would integrate with email service
        return {"message": "Email queued for sending", "note": "Integration with email service needed"}

    async def _create_proposal(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        args: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        from app.services.ai.proposal_generator import ProposalGeneratorService
        
        service = ProposalGeneratorService()
        proposal = await service.generate_proposal(
            db, UUID(args["deal_id"]), tenant_id, user_id,
            UUID(args["template_id"]) if args.get("template_id") else None,
            correlation_id=correlation_id,
        )
        return {"id": str(proposal.id), "message": "Proposal generated"}

    async def _update_stage(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        args: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        deal_id = UUID(args["deal_id"])
        stage_id = UUID(args["stage_id"])

        result = await db.execute(
            select(Deal).where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
        )
        deal = result.scalar_one_or_none()
        if not deal:
            raise ValueError(f"Deal {deal_id} not found")

        deal.stage_id = stage_id
        await db.commit()

        return {"message": f"Deal moved to stage {stage_id}"}

    async def _search_contacts(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        args: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        query = select(Contact).where(Contact.tenant_id == tenant_id).options(
            selectinload(Contact.company)
        )

        if args.get("query"):
            search = f"%{args['query']}%"
            query = query.where(
                or_(
                    Contact.first_name.ilike(search),
                    Contact.last_name.ilike(search),
                    Contact.email.ilike(search),
                )
            )

        if args.get("company_id"):
            query = query.where(Contact.company_id == UUID(args["company_id"]))

        limit = min(args.get("limit", 20), 100)
        query = query.limit(limit)

        result = await db.execute(query)
        contacts = result.scalars().all()

        return {
            "contacts": [
                {
                    "id": str(c.id),
                    "name": c.full_name,
                    "email": c.email,
                    "title": c.title,
                    "company": c.company.name if c.company else None,
                }
                for c in contacts
            ],
            "count": len(contacts),
        }

    async def _get_deal(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        args: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        deal_id = UUID(args["deal_id"])
        
        result = await db.execute(
            select(Deal)
            .where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
            .options(
                selectinload(Deal.contact).selectinload(Contact.company),
                selectinload(Deal.company),
                selectinload(Deal.stage),
                selectinload(Deal.pipeline),
                selectinload(Deal.owner),
            )
        )
        deal = result.scalar_one_or_none()
        if not deal:
            raise ValueError(f"Deal {deal_id} not found")

        return {
            "id": str(deal.id),
            "title": deal.title,
            "value": deal.value,
            "currency": deal.currency,
            "stage": deal.stage.name if deal.stage else None,
            "pipeline": deal.pipeline.name if deal.pipeline else None,
            "probability": deal.probability,
            "expected_close": deal.expected_close_date.isoformat() if deal.expected_close_date else None,
            "contact": deal.contact.full_name if deal.contact else None,
            "company": deal.company.name if deal.company else None,
        }

    async def _search_companies(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        args: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        query = select(Company).where(Company.tenant_id == tenant_id)

        if args.get("query"):
            search = f"%{args['query']}%"
            query = query.where(
                or_(
                    Company.name.ilike(search),
                    Company.domain.ilike(search),
                )
            )

        if args.get("industry"):
            query = query.where(Company.industry == args["industry"])

        if args.get("size"):
            query = query.where(Company.size == args["size"])

        limit = min(args.get("limit", 20), 100)
        query = query.limit(limit)

        result = await db.execute(query)
        companies = result.scalars().all()

        return {
            "companies": [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "domain": c.domain,
                    "industry": c.industry,
                    "size": c.size,
                }
                for c in companies
            ],
            "count": len(companies),
        }


# Need imports
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from app.models import Lead, Contact, Company, Deal, Campaign, Task, User, Membership, RoleEnum, CampaignTypeEnum, CampaignAudience, CampaignTemplate
from datetime import timedelta
import json