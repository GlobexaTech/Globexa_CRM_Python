from sqlalchemy.orm import selectinload
"""
AI Next-Best-Action Service for Globexa CRM.
Provides explainable recommendations for lead actions.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone, timedelta
from enum import Enum
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import Lead, Contact, Company, Activity, ActivityTypeEnum, Deal
from app.services.ai.router import get_ai_router, AITaskTypeEnum

logger = structlog.get_logger()


class NextActionType(str, Enum):
    """Next action types per blueprint."""
    CALL = "call"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SCHEDULE_DEMO = "schedule_demo"
    SEND_PROPOSAL = "send_proposal"
    NURTURE = "nurture"
    WAIT = "wait"
    DISQUALIFY = "disqualify"
    ESCALATE = "escalate"


@dataclass
class NextActionRecommendation:
    """Next best action recommendation."""
    lead_id: UUID
    action: NextActionType
    reasoning: str
    confidence: float  # 0-1
    timeline: str  # within_2_hours, today, this_week, next_week
    priority: int  # 1-10
    details: Dict[str, Any]  # Action-specific details
    factors: List[Dict[str, Any]]
    model_version: str
    recommended_at: datetime


class NextBestActionService:
    """AI-powered next best action recommendations."""

    def __init__(self):
        self.router = get_ai_router()

    async def get_recommendation(
        self,
        db: AsyncSession,
        lead_id: UUID,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> NextActionRecommendation:
        """Get next best action for a lead."""
        # Load lead with full context
        result = await db.execute(
            select(Lead)
            .where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
            .options(
                selectinload(Lead.contact).selectinload(Contact.company),
                selectinload(Lead.company),
                selectinload(Lead.owner),
            )
        )
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Get recent activities
        activities_result = await db.execute(
            select(Activity)
            .where(Activity.tenant_id == tenant_id, Activity.lead_id == lead_id)
            .order_by(Activity.created_at.desc())
            .limit(20)
        )
        activities = activities_result.scalars().all()

        # Get deal info if converted
        deal = None
        if lead.converted_deal_id:
            deal_result = await db.execute(
                select(Deal).where(Deal.id == lead.converted_deal_id)
            )
            deal = deal_result.scalar_one_or_none()

        # Build context for AI
        context = self._build_context(lead, activities, deal)

        # Get AI recommendation
        ai_result = await self._get_ai_recommendation(
            db, lead, context, tenant_id, user_id, correlation_id
        )

        # Validate and enhance with rules
        recommendation = self._validate_and_enhance(ai_result, lead, activities, context)

        # Save to lead
        lead.ai_next_action = recommendation.reasoning
        lead.ai_next_action_confidence = recommendation.confidence
        await db.commit()

        # Create activity
        from app.models import Activity as ActivityModel, ActivityTypeEnum
        activity = ActivityModel(
            tenant_id=tenant_id,
            lead_id=lead_id,
            type=ActivityTypeEnum.AI_ACTION,
            subject=f"AI Recommendation: {recommendation.action.value}",
            description=f"Next best action: {recommendation.reasoning}",
            metadata={
                "action": recommendation.action.value,
                "confidence": recommendation.confidence,
                "timeline": recommendation.timeline,
                "priority": recommendation.priority,
            },
            is_ai_generated=True,
            ai_provider="nvidia",
            ai_model="nemotron-3-ultra",
        )
        db.add(activity)
        await db.commit()

        return recommendation

    def _build_context(
        self,
        lead: Lead,
        activities: List[Activity],
        deal: Optional[Deal],
    ) -> Dict[str, Any]:
        """Build context for AI recommendation."""
        # Analyze activities
        email_activities = [a for a in activities if a.type in [
            ActivityTypeEnum.EMAIL, ActivityTypeEnum.EMAIL_OPENED,
            ActivityTypeEnum.EMAIL_CLICKED, ActivityTypeEnum.EMAIL_REPLIED,
        ]]
        
        call_activities = [a for a in activities if a.type == ActivityTypeEnum.CALL]
        meeting_activities = [a for a in activities if a.type == ActivityTypeEnum.MEETING]
        reply_activities = [a for a in activities if a.type == ActivityTypeEnum.EMAIL_REPLIED]

        last_activity = activities[0] if activities else None
        days_since_activity = None
        if last_activity:
            days_since_activity = (datetime.now(timezone.utc) - last_activity.created_at).days

        # Engagement metrics
        emails_sent = len([a for a in email_activities if a.type == ActivityTypeEnum.EMAIL])
        emails_opened = len([a for a in email_activities if a.type == ActivityTypeEnum.EMAIL_OPENED])
        emails_clicked = len([a for a in email_activities if a.type == ActivityTypeEnum.EMAIL_CLICKED])
        emails_replied = len(reply_activities)

        # Last reply analysis
        last_reply = reply_activities[0] if reply_activities else None
        last_reply_sentiment = None
        last_reply_intent = None
        if last_reply and last_reply.metadata:
            last_reply_sentiment = last_reply.metadata.get("sentiment")
            last_reply_intent = last_reply.metadata.get("intent")

        return {
            "lead": {
                "id": str(lead.id),
                "title": lead.title,
                "status": lead.status.value,
                "ai_score": lead.ai_score,
                "is_qualified": lead.is_qualified,
                "source": lead.source.value if lead.source else None,
                "owner": lead.owner.full_name if lead.owner else None,
            },
            "contact": {
                "name": lead.contact.full_name if lead.contact else None,
                "title": lead.contact.title if lead.contact else None,
                "company": lead.contact.company.name if lead.contact and lead.contact.company else None,
            } if lead.contact else None,
            "company": {
                "name": lead.company.name if lead.company else None,
                "industry": lead.company.industry if lead.company else None,
                "size": lead.company.size if lead.company else None,
            } if lead.company else None,
            "engagement": {
                "emails_sent": emails_sent,
                "emails_opened": emails_opened,
                "emails_clicked": emails_clicked,
                "emails_replied": emails_replied,
                "open_rate": emails_opened / emails_sent if emails_sent > 0 else 0,
                "click_rate": emails_clicked / emails_sent if emails_sent > 0 else 0,
                "reply_rate": emails_replied / emails_sent if emails_sent > 0 else 0,
                "calls_made": len(call_activities),
                "meetings_held": len(meeting_activities),
                "days_since_last_activity": days_since_activity,
            },
            "last_reply": {
                "sentiment": last_reply_sentiment,
                "intent": last_reply_intent,
                "content": last_reply.description[:500] if last_reply and last_reply.description else None,
            } if last_reply else None,
            "deal": {
                "stage": deal.stage.name if deal and deal.stage else None,
                "value": deal.value if deal else None,
                "probability": deal.probability if deal else None,
            } if deal else None,
            "ai_score": lead.ai_score,
            "ai_next_action": lead.ai_next_action,
        }

    async def _get_ai_recommendation(
        self,
        db: AsyncSession,
        lead: Lead,
        context: Dict[str, Any],
        tenant_id: UUID,
        user_id: Optional[UUID],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        """Get AI recommendation for next action."""
        prompt = f"""
        You are a sales AI assistant. Recommend the next best action for this lead.
        
        Lead Context:
        {context}
        
        Available actions: call, email, whatsapp, schedule_demo, send_proposal, nurture, wait, disqualify, escalate
        
        Consider:
        - Lead status and AI score
        - Engagement history (opens, clicks, replies)
        - Last reply sentiment and intent
        - Time since last activity
        - Deal stage if exists
        - Owner workload (from context)
        - Best practices: reply within 2 hours for hot leads, nurture cold leads, escalate stuck deals
        
        Return JSON:
        {{
            "action": "call|email|whatsapp|schedule_demo|send_proposal|nurture|wait|disqualify|escalate",
            "reasoning": "Detailed explanation of why this action",
            "confidence": 0.92,
            "timeline": "within_2_hours|today|this_week|next_week",
            "priority": 9,
            "details": {{"subject": "...", "template": "..."}}  // action-specific
        }}
        """

        result = await self.router.complete(
            task_type=AITaskTypeEnum.NEXT_BEST_ACTION,
            prompt=prompt,
            tenant_id=tenant_id,
            user_id=user_id,
            correlation_id=correlation_id,
            response_format={"type": "json_object"},
            temperature=0.3,
            db=db,
        )

        if result.success:
            import json
            try:
                return json.loads(result.content)
            except json.JSONDecodeError:
                pass

        # Fallback
        return {
            "action": "email",
            "reasoning": "Default to email follow-up",
            "confidence": 0.5,
            "timeline": "today",
            "priority": 5,
            "details": {},
        }

    def _validate_and_enhance(
        self,
        ai_result: Dict[str, Any],
        lead: Lead,
        activities: List[Activity],
        context: Dict[str, Any],
    ) -> NextActionRecommendation:
        """Validate AI recommendation and enhance with rules."""
        action_str = ai_result.get("action", "email")
        try:
            action = NextActionType(action_str)
        except ValueError:
            action = NextActionType.EMAIL

        confidence = min(max(ai_result.get("confidence", 0.5), 0.0), 1.0)
        timeline = ai_result.get("timeline", "today")
        priority = min(max(ai_result.get("priority", 5), 1), 10)
        details = ai_result.get("details", {})
        reasoning = ai_result.get("reasoning", "AI recommended action")

        # Rule-based enhancements
        engagement = context.get("engagement", {})
        last_reply = context.get("last_reply")
        days_since = engagement.get("days_since_last_activity", 999)

        # Override for hot leads with replies
        if last_reply and last_reply.get("intent") in ["interested", "meeting_request", "pricing_objection"]:
            if action == NextActionType.NURTURE:
                action = NextActionType.CALL
                confidence = max(confidence, 0.9)
                reasoning = "Hot lead with positive reply - immediate call required"
                timeline = "within_2_hours"
                priority = 10

        # Override for pricing objections
        if last_reply and last_reply.get("intent") == "pricing_objection":
            action = NextActionType.CALL
            details = {"talking_points": ["Value justification", "ROI calculator", "Flexible terms"]}
            reasoning = "Pricing objection requires personal conversation"
            timeline = "within_2_hours"

        # Override for meeting requests
        if last_reply and last_reply.get("intent") == "meeting_request":
            action = NextActionType.SCHEDULE_DEMO
            details = {"proposed_times": ["Tomorrow 10am", "Tomorrow 2pm", "Friday 11am"]}
            reasoning = "Lead requested meeting - schedule immediately"
            timeline = "within_2_hours"

        # Override for unqualified/disqualified
        if lead.status.value in ["unqualified", "lost"] or lead.ai_score and lead.ai_score < 20:
            action = NextActionType.DISQUALIFY
            confidence = max(confidence, 0.8)
            reasoning = "Lead disqualified based on score/status"
            timeline = "today"

        # Override for stalled deals
        if days_since > 14 and engagement.get("emails_replied", 0) == 0:
            if action in [NextActionType.EMAIL, NextActionType.NURTURE]:
                action = NextActionType.ESCALATE
                details = {"escalate_to": "sales_manager", "reason": "No engagement for 2+ weeks"}
                reasoning = "Lead stalled - escalate to manager"
                timeline = "today"

        # Add action-specific defaults
        if action == NextActionType.CALL and "script" not in details:
            details["script"] = "Discovery call: Pain points, timeline, budget, authority"
        elif action == NextActionType.EMAIL and "template" not in details:
            details["template"] = "Follow-up with value add (case study, article, insight)"
        elif action == NextActionType.SCHEDULE_DEMO and "proposed_times" not in details:
            details["proposed_times"] = ["Tomorrow 10am", "Tomorrow 2pm", "Friday 11am"]
        elif action == NextActionType.SEND_PROPOSAL and "proposal_template" not in details:
            details["proposal_template"] = "Standard proposal with ROI section"

        factors = [
            {"factor": "AI Score", "value": lead.ai_score, "impact": "high" if lead.ai_score and lead.ai_score > 70 else "medium"},
            {"factor": "Last Reply Intent", "value": last_reply.get("intent") if last_reply else None, "impact": "high"},
            {"factor": "Engagement Level", "value": "high" if engagement.get("emails_replied", 0) > 0 else "low", "impact": "high"},
            {"factor": "Days Since Activity", "value": days_since, "impact": "medium"},
        ]

        return NextActionRecommendation(
            lead_id=lead.id,
            action=action,
            reasoning=reasoning,
            confidence=confidence,
            timeline=timeline,
            priority=priority,
            details=details,
            factors=factors,
            model_version="v1.0",
            recommended_at=datetime.now(timezone.utc),
        )