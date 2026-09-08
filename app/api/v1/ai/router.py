"""
AI API routes for Globexa CRM.
All AI capabilities exposed via REST API.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.deps import get_current_active_user, get_tenant_id, require_ai_scoring, require_ai_chat, require_leads_read, require_leads_write, require_deals_write, require_campaigns_write
from app.services.ai import (
    LeadScoringService,
    AutoAssignmentService,
    NextBestActionService,
    ReplyAnalysisService,
    LeadMinerService,
    ProposalGeneratorService,
    AIAssistantService,
    LeadScoreResult,
    AssignmentResult,
    NextActionRecommendation,
    ReplyAnalysis,
    ReplyResponse,
    LeadMinerResult,
    ICPDefinition,
    DiscoveredProspect,
)
from app.services.ai.assistant import AIAssistantService, AssistantMessage

async def require_durable_ai_contract(request: Request):
    if request.method == "POST":
        raise HTTPException(410, "Use /api/v1/operations/ai/requests with Idempotency-Key; poll the returned job")


router = APIRouter(prefix="/ai", tags=["AI"], dependencies=[Depends(require_durable_ai_contract)])

# Service instances
lead_scoring_service = LeadScoringService()
auto_assignment_service = AutoAssignmentService()
next_best_action_service = NextBestActionService()
reply_analysis_service = ReplyAnalysisService()
lead_miner_service = LeadMinerService()
proposal_generator_service = ProposalGeneratorService()
assistant_service = AIAssistantService()


# =============================================================================
# Lead Scoring
# =============================================================================

class ScoreLeadRequest(BaseModel):
    correlation_id: Optional[str] = None


@router.post("/leads/{lead_id}/score", response_model=dict)
async def score_lead(
    lead_id: UUID,
    request: ScoreLeadRequest,
    current_user: tuple = Depends(require_ai_scoring),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Score a lead with explainable factors."""
    user, _ = current_user
    
    result = await lead_scoring_service.score_lead(
        db, lead_id, tenant_id, user.id, request.correlation_id
    )
    
    return {
        "lead_id": str(result.lead_id),
        "score": result.score,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "recommended_action": result.recommended_action,
        "factors": [
            {
                "name": f.name,
                "category": f.category,
                "score": f.score,
                "weight": f.weight,
                "evidence": f.evidence,
            }
            for f in result.factors
        ],
        "model_version": result.model_version,
        "scored_at": result.scored_at.isoformat(),
    }


# =============================================================================
# Auto Assignment
# =============================================================================

class AssignLeadRequest(BaseModel):
    override_rules: Optional[dict] = None
    correlation_id: Optional[str] = None


@router.post("/leads/{lead_id}/assign", response_model=dict)
async def assign_lead(
    lead_id: UUID,
    request: AssignLeadRequest,
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Auto-assign a lead to best salesperson."""
    user, _ = current_user
    
    result = await auto_assignment_service.assign_lead(
        db, lead_id, tenant_id, user.id, request.correlation_id, request.override_rules
    )
    
    return {
        "lead_id": str(result.lead_id),
        "assigned_user_id": str(result.assigned_user_id),
        "assigned_user_name": result.assigned_user_name,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "factors": [
            {
                "name": f.name,
                "score": f.score,
                "weight": f.weight,
                "evidence": f.evidence,
            }
            for f in result.factors
        ],
        "alternative_candidates": result.alternative_candidates,
        "model_version": result.model_version,
        "assigned_at": result.assigned_at.isoformat(),
    }


# =============================================================================
# Next Best Action
# =============================================================================

class NextActionRequest(BaseModel):
    correlation_id: Optional[str] = None


@router.post("/leads/{lead_id}/next-action", response_model=dict)
async def get_next_action(
    lead_id: UUID,
    request: NextActionRequest,
    current_user: tuple = Depends(require_leads_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get next best action recommendation for a lead."""
    user, _ = current_user
    
    result = await next_best_action_service.get_recommendation(
        db, lead_id, tenant_id, user.id, request.correlation_id
    )
    
    return {
        "lead_id": str(result.lead_id),
        "action": result.action.value,
        "reasoning": result.reasoning,
        "confidence": result.confidence,
        "timeline": result.timeline,
        "priority": result.priority,
        "details": result.details,
        "factors": result.factors,
        "model_version": result.model_version,
        "recommended_at": result.recommended_at.isoformat(),
    }


# =============================================================================
# Reply Analysis
# =============================================================================

class AnalyzeReplyRequest(BaseModel):
    reply_text: str
    email_metadata: Optional[dict] = None
    correlation_id: Optional[str] = None


@router.post("/leads/{lead_id}/analyze-reply", response_model=dict)
async def analyze_reply(
    lead_id: UUID,
    request: AnalyzeReplyRequest,
    current_user: tuple = Depends(require_leads_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Analyze inbound reply for intent, sentiment, and next steps."""
    user, _ = current_user
    
    result = await reply_analysis_service.analyze_reply(
        db, lead_id, request.reply_text, tenant_id, user.id, request.correlation_id, request.email_metadata
    )
    
    return {
        "intent": result.intent.value,
        "sentiment": result.sentiment.value,
        "purchase_probability": result.purchase_probability,
        "questions": result.questions,
        "key_points": result.key_points,
        "urgency": result.urgency,
        "recommended_stage": result.recommended_stage,
        "recommended_action": result.recommended_action,
        "confidence": result.confidence,
        "entities": result.entities,
        "language": result.language,
    }


class GenerateResponseRequest(BaseModel):
    reply_text: str
    response_type: str = "draft"  # auto, draft, requires_approval
    correlation_id: Optional[str] = None


@router.post("/leads/{lead_id}/generate-response", response_model=dict)
async def generate_response(
    lead_id: UUID,
    request: GenerateResponseRequest,
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Generate response to inbound reply."""
    user, _ = current_user
    
    result = await reply_analysis_service.generate_response(
        db, lead_id, request.reply_text, tenant_id, user.id, request.correlation_id, 
        response_type=request.response_type
    )
    
    return {
        "subject": result.subject,
        "body": result.body,
        "response_type": result.response_type,
        "confidence": result.confidence,
        "template_used": result.template_used,
    }


# =============================================================================
# Lead Miner
# =============================================================================

class RunLeadMinerRequest(BaseModel):
    icp_definition: dict
    max_prospects: int = 50
    min_score_threshold: int = 85
    correlation_id: Optional[str] = None


@router.post("/lead-miner/run", response_model=dict)
async def run_lead_miner(
    request: RunLeadMinerRequest,
    current_user: tuple = Depends(require_ai_scoring),  # Reuse AI scoring permission
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Run AI Lead Miner to discover prospects matching ICP."""
    user, _ = current_user
    
    # Parse ICP definition
    icp = ICPDefinition(**request.icp_definition)
    
    result = await lead_miner_service.run_lead_miner(
        db, tenant_id, icp, user.id, 
        request.max_prospects, request.min_score_threshold, request.correlation_id
    )
    
    return {
        "icp_id": str(result.icp_id),
        "prospects_found": result.prospects_found,
        "prospects_qualified": result.prospects_qualified,
        "prospects_created": result.prospects_created,
        "execution_time_seconds": result.execution_time_seconds,
        "cost_usd": result.cost_usd,
    }


# =============================================================================
# Proposal Generator
# =============================================================================

class GenerateProposalRequest(BaseModel):
    template_id: Optional[str] = None
    customizations: Optional[dict] = None
    correlation_id: Optional[str] = None


@router.post("/deals/{deal_id}/generate-proposal", response_model=dict)
async def generate_proposal(
    deal_id: UUID,
    request: GenerateProposalRequest,
    current_user: tuple = Depends(require_deals_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Generate a proposal for a deal."""
    user, _ = current_user
    
    proposal = await proposal_generator_service.generate_proposal(
        db, deal_id, tenant_id, user.id,
        UUID(request.template_id) if request.template_id else None,
        request.customizations, request.correlation_id
    )
    
    return {
        "id": str(proposal.id),
        "title": proposal.title,
        "status": proposal.status,
        "version": proposal.version,
        "executive_summary": proposal.executive_summary,
        "solution_overview": proposal.solution_overview,
        "pricing_details": proposal.pricing_details,
        "terms": proposal.terms,
        "expires_at": proposal.expires_at.isoformat() if proposal.expires_at else None,
        "is_ai_generated": proposal.is_ai_generated,
    }


class RegenerateProposalSectionRequest(BaseModel):
    section: str  # executive_summary, solution_overview, pricing, terms
    instructions: str
    correlation_id: Optional[str] = None


@router.post("/proposals/{proposal_id}/regenerate", response_model=dict)
async def regenerate_proposal_section(
    proposal_id: UUID,
    request: RegenerateProposalSectionRequest,
    current_user: tuple = Depends(require_deals_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Regenerate a specific section of a proposal."""
    user, _ = current_user
    
    result = await proposal_generator_service.regenerate_section(
        db, proposal_id, request.section, request.instructions,
        tenant_id, user.id, request.correlation_id
    )
    
    return result


# =============================================================================
# AI Assistant (Chat)
# =============================================================================

class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[dict]] = None
    correlation_id: Optional[str] = None


@router.post("/chat", response_model=dict)
async def chat_with_assistant(
    request: ChatRequest,
    current_user: tuple = Depends(require_ai_chat),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Chat with the AI Assistant."""
    user, _ = current_user
    
    # Parse conversation history
    history = None
    if request.conversation_history:
        history = [AssistantMessage(**msg) for msg in request.conversation_history]
    
    result = await assistant_service.chat(
        db, tenant_id, user.id, request.message, history, request.correlation_id
    )
    
    return {
        "message": result.message,
        "tool_calls": [
            {
                "name": tc.name,
                "arguments": tc.arguments,
                "call_id": tc.call_id,
            }
            for tc in (result.tool_calls or [])
        ] if result.tool_calls else None,
        "tool_results": [
            {
                "name": tr.name,
                "result": tr.result,
                "error": tr.error,
            }
            for tr in (result.tool_results or [])
        ] if result.tool_results else None,
    }


# =============================================================================
# Batch Operations
# =============================================================================

class BatchScoreLeadsRequest(BaseModel):
    lead_ids: List[str]
    correlation_id: Optional[str] = None


@router.post("/leads/batch-score", response_model=dict)
async def batch_score_leads(
    request: BatchScoreLeadsRequest,
    current_user: tuple = Depends(require_ai_scoring),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Score multiple leads in batch."""
    user, _ = current_user
    
    results = []
    for lead_id_str in request.lead_ids:
        try:
            result = await lead_scoring_service.score_lead(
                db, UUID(lead_id_str), tenant_id, user.id, request.correlation_id
            )
            results.append({
                "lead_id": lead_id_str,
                "score": result.score,
                "confidence": result.confidence,
                "recommended_action": result.recommended_action,
            })
        except Exception as e:
            results.append({
                "lead_id": lead_id_str,
                "error": str(e),
            })
    
    return {"results": results, "total": len(results)}


class BatchAssignLeadsRequest(BaseModel):
    lead_ids: List[str]
    correlation_id: Optional[str] = None


@router.post("/leads/batch-assign", response_model=dict)
async def batch_assign_leads(
    request: BatchAssignLeadsRequest,
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Auto-assign multiple leads."""
    user, _ = current_user
    
    results = []
    for lead_id_str in request.lead_ids:
        try:
            result = await auto_assignment_service.assign_lead(
                db, UUID(lead_id_str), tenant_id, user.id, request.correlation_id
            )
            results.append({
                "lead_id": lead_id_str,
                "assigned_user_id": str(result.assigned_user_id),
                "assigned_user_name": result.assigned_user_name,
                "confidence": result.confidence,
            })
        except Exception as e:
            results.append({
                "lead_id": lead_id_str,
                "error": str(e),
            })
    
    return {"results": results, "total": len(results)}


# =============================================================================
# AI Usage Analytics
# =============================================================================

@router.get("/usage/analytics", response_model=dict)
async def get_ai_usage_analytics(
    days: int = Query(30, ge=1, le=365),
    current_user: tuple = Depends(require_ai_chat),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get AI usage analytics for tenant."""
    from app.models import AIUsageLog, AITaskTypeEnum, AIProviderEnum
    from sqlalchemy import select, func
    from datetime import datetime, timezone, timedelta
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Total usage by task type
    task_result = await db.execute(
        select(
            AIUsageLog.task_type,
            func.count().label("count"),
            func.sum(AIUsageLog.total_tokens).label("tokens"),
            func.sum(AIUsageLog.estimated_cost_usd).label("cost"),
            func.avg(AIUsageLog.latency_ms).label("avg_latency"),
        )
        .where(
            AIUsageLog.tenant_id == tenant_id,
            AIUsageLog.created_at >= cutoff,
        )
        .group_by(AIUsageLog.task_type)
    )
    
    # Total usage by provider
    provider_result = await db.execute(
        select(
            AIUsageLog.provider,
            func.count().label("count"),
            func.sum(AIUsageLog.total_tokens).label("tokens"),
            func.sum(AIUsageLog.estimated_cost_usd).label("cost"),
        )
        .where(
            AIUsageLog.tenant_id == tenant_id,
            AIUsageLog.created_at >= cutoff,
        )
        .group_by(AIUsageLog.provider)
    )
    
    # Daily usage
    daily_result = await db.execute(
        select(
            func.date(AIUsageLog.created_at).label("date"),
            func.count().label("count"),
            func.sum(AIUsageLog.total_tokens).label("tokens"),
            func.sum(AIUsageLog.estimated_cost_usd).label("cost"),
        )
        .where(
            AIUsageLog.tenant_id == tenant_id,
            AIUsageLog.created_at >= cutoff,
        )
        .group_by(func.date(AIUsageLog.created_at))
        .order_by(func.date(AIUsageLog.created_at))
    )
    
    return {
        "period_days": days,
        "by_task_type": [
            {
                "task_type": row[0].value,
                "count": row[1],
                "tokens": row[2] or 0,
                "cost_usd": float(row[3] or 0),
                "avg_latency_ms": float(row[4] or 0),
            }
            for row in task_result.fetchall()
        ],
        "by_provider": [
            {
                "provider": row[0].value,
                "count": row[1],
                "tokens": row[2] or 0,
                "cost_usd": float(row[3] or 0),
            }
            for row in provider_result.fetchall()
        ],
        "daily": [
            {
                "date": row[0].isoformat() if row[0] else None,
                "count": row[1],
                "tokens": row[2] or 0,
                "cost_usd": float(row[3] or 0),
            }
            for row in daily_result.fetchall()
        ],
    }
