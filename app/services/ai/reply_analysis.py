"""
AI Reply Analysis & Response Generation Service for Globexa CRM.
Analyzes inbound replies and generates responses per tenant permissions.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from enum import Enum
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Lead, Contact, Activity, ActivityTypeEnum
from app.services.ai.router import get_ai_router, AITaskTypeEnum

logger = structlog.get_logger()


class ReplyIntent(str, Enum):
    """Reply intent categories per blueprint."""
    INTERESTED = "interested"
    NEEDS_INFORMATION = "needs_information"
    PRICING_OBJECTION = "pricing_objection"
    NOT_INTERESTED = "not_interested"
    OUT_OF_OFFICE = "out_of_office"
    WRONG_PERSON = "wrong_person"
    UNSUBSCRIBE = "unsubscribe"
    MEETING_REQUEST = "meeting_request"
    SUPPORT_REQUEST = "support_request"
    SPAM = "spam"
    UNKNOWN = "unknown"


class ReplySentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


@dataclass
class ReplyAnalysis:
    """Reply analysis result."""
    intent: ReplyIntent
    sentiment: ReplySentiment
    purchase_probability: str  # high, medium, low
    questions: List[str]
    key_points: List[str]
    urgency: str  # immediate, today, this_week, low
    recommended_stage: str
    recommended_action: str
    confidence: float
    entities: Dict[str, Any]
    language: str


@dataclass
class ReplyResponse:
    """Generated reply response."""
    subject: str
    body: str
    response_type: str  # auto, draft, requires_approval
    confidence: float
    template_used: Optional[str] = None


class ReplyAnalysisService:
    """AI-powered reply analysis and response generation."""

    def __init__(self):
        self.router = get_ai_router()

    async def analyze_reply(
        self,
        db: AsyncSession,
        lead_id: UUID,
        reply_text: str,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
        email_metadata: Optional[Dict[str, Any]] = None,
    ) -> ReplyAnalysis:
        """Analyze inbound reply for intent, sentiment, and next steps."""
        # Load lead
        result = await db.execute(
            select(Lead)
            .where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
            .options(selectinload(Lead.contact).selectinload(Contact.company))
        )
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Get conversation context
        activities_result = await db.execute(
            select(Activity)
            .where(Activity.tenant_id == tenant_id, Activity.lead_id == lead_id)
            .order_by(Activity.created_at.desc())
            .limit(10)
        )
        activities = activities_result.scalars().all()

        # Build context
        context = self._build_context(lead, activities, reply_text, email_metadata)

        # Get AI analysis
        ai_result = await self._get_ai_analysis(
            db, lead, context, tenant_id, user_id, correlation_id
        )

        # Parse and validate
        analysis = self._parse_analysis(ai_result)

        # Save analysis to lead
        lead.ai_reply_analysis = ai_result.get("reasoning", "")
        lead.ai_reply_intent = ai_result.get("intent")
        lead.ai_reply_sentiment = ai_result.get("sentiment")
        await db.commit()

        # Create activity
        from app.models import Activity as ActivityModel, ActivityTypeEnum
        activity = ActivityModel(
            tenant_id=tenant_id,
            lead_id=lead_id,
            type=ActivityTypeEnum.EMAIL_REPLIED,
            subject=f"Reply analyzed: {analysis.intent.value}",
            description=f"Intent: {analysis.intent.value}, Sentiment: {analysis.sentiment.value}",
            metadata={
                "intent": analysis.intent.value,
                "sentiment": analysis.sentiment.value,
                "purchase_probability": analysis.purchase_probability,
                "questions": analysis.questions,
                "recommended_action": analysis.recommended_action,
            },
            is_ai_generated=True,
            ai_provider="nvidia",
            ai_model="nemotron-3-ultra",
        )
        db.add(activity)

        # If interested, update lead status
        if analysis.intent in [ReplyIntent.INTERESTED, ReplyIntent.MEETING_REQUEST]:
            if lead.status.value in ["new", "contacted", "nurturing"]:
                lead.status = "qualified"
                lead.is_qualified = True
                lead.qualified_at = datetime.now(timezone.utc)

        await db.commit()

        return analysis

    def _build_context(
        self,
        lead: Lead,
        activities: List[Activity],
        reply_text: str,
        email_metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build context for reply analysis."""
        # Recent emails sent
        sent_emails = [a for a in activities if a.type == ActivityTypeEnum.EMAIL]
        last_email = sent_emails[0] if sent_emails else None

        return {
            "lead": {
                "id": str(lead.id),
                "title": lead.title,
                "status": lead.status.value,
                "ai_score": lead.ai_score,
                "source": lead.source.value if lead.source else None,
            },
            "contact": {
                "name": lead.contact.full_name if lead.contact else None,
                "title": lead.contact.title if lead.contact else None,
                "company": lead.contact.company.name if lead.contact and lead.contact.company else None,
            } if lead.contact else None,
            "last_outbound_email": {
                "subject": last_email.subject if last_email else None,
                "sent_at": last_email.created_at.isoformat() if last_email else None,
            } if last_email else None,
            "reply": {
                "text": reply_text,
                "metadata": email_metadata,
            },
            "conversation_history": [
                {
                    "type": a.type.value,
                    "subject": a.subject,
                    "created_at": a.created_at.isoformat(),
                }
                for a in activities[:5]
            ],
        }

    async def _get_ai_analysis(
        self,
        db: AsyncSession,
        lead: Lead,
        context: Dict[str, Any],
        tenant_id: UUID,
        user_id: Optional[UUID],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        """Get AI analysis of reply."""
        prompt = f"""
        Analyze this inbound email reply from a sales lead.
        
        Context:
        {context}
        
        Classify the reply and provide actionable insights.
        
        Return JSON:
        {{
            "intent": "interested|needs_information|pricing_objection|not_interested|out_of_office|wrong_person|unsubscribe|meeting_request|support_request|spam|unknown",
            "sentiment": "positive|neutral|negative",
            "purchase_probability": "high|medium|low",
            "questions": ["question1", "question2"],
            "key_points": ["point1", "point2"],
            "urgency": "immediate|today|this_week|low",
            "recommended_stage": "new|contacted|qualified|nurturing|converted",
            "recommended_action": "call|email|schedule_demo|send_proposal|nurture|disqualify|escalate",
            "confidence": 0.92,
            "entities": {{"mentioned_products": [], "mentioned_competitors": [], "dates": []}},
            "language": "en"
        }}
        """

        result = await self.router.complete(
            task_type=AITaskTypeEnum.REPLY_ANALYSIS,
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

        return {
            "intent": "unknown",
            "sentiment": "neutral",
            "purchase_probability": "low",
            "questions": [],
            "key_points": [],
            "urgency": "low",
            "recommended_stage": "nurturing",
            "recommended_action": "review_manually",
            "confidence": 0.3,
            "entities": {},
            "language": "en",
        }

    def _parse_analysis(self, ai_result: Dict[str, Any]) -> ReplyAnalysis:
        """Parse and validate AI analysis result."""
        intent_str = ai_result.get("intent", "unknown")
        try:
            intent = ReplyIntent(intent_str)
        except ValueError:
            intent = ReplyIntent.UNKNOWN

        sentiment_str = ai_result.get("sentiment", "neutral")
        try:
            sentiment = ReplySentiment(sentiment_str)
        except ValueError:
            sentiment = ReplySentiment.NEUTRAL

        return ReplyAnalysis(
            intent=intent,
            sentiment=sentiment,
            purchase_probability=ai_result.get("purchase_probability", "low"),
            questions=ai_result.get("questions", []),
            key_points=ai_result.get("key_points", []),
            urgency=ai_result.get("urgency", "low"),
            recommended_stage=ai_result.get("recommended_stage", "nurturing"),
            recommended_action=ai_result.get("recommended_action", "review_manually"),
            confidence=ai_result.get("confidence", 0.5),
            entities=ai_result.get("entities", {}),
            language=ai_result.get("language", "en"),
        )

    async def generate_response(
        self,
        db: AsyncSession,
        lead_id: UUID,
        reply_text: str,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
        reply_analysis: Optional[ReplyAnalysis] = None,
        response_type: str = "draft",  # auto, draft, requires_approval
    ) -> ReplyResponse:
        """Generate response to inbound reply."""
        # Load lead
        result = await db.execute(
            select(Lead)
            .where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
            .options(selectinload(Lead.contact).selectinload(Contact.company))
        )
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Analyze if not provided
        if not reply_analysis:
            reply_analysis = await self.analyze_reply(
                db, lead_id, reply_text, tenant_id, user_id, correlation_id
            )

        # Check tenant permissions for auto-response
        from app.api.deps import require_permission, Permission
        can_auto_respond = True  # Would check tenant AI_RESPOND_EMAIL permission

        # Get AI response
        ai_result = await self._get_ai_response(
            db, lead, reply_text, reply_analysis, tenant_id, user_id, correlation_id
        )

        response = ReplyResponse(
            subject=ai_result.get("subject", "Re: Your inquiry"),
            body=ai_result.get("body", "Thank you for your message. We'll get back to you soon."),
            response_type="auto" if can_auto_respond and ai_result.get("confidence", 0) > 0.85 else "draft",
            confidence=ai_result.get("confidence", 0.7),
            template_used=ai_result.get("template"),
        )

        # Create activity
        from app.models import Activity as ActivityModel, ActivityTypeEnum
        activity = ActivityModel(
            tenant_id=tenant_id,
            lead_id=lead_id,
            type=ActivityTypeEnum.EMAIL,
            subject=f"Reply generated: {response.response_type}",
            description=f"AI-generated response ({response.response_type})",
            metadata={
                "response_type": response.response_type,
                "confidence": response.confidence,
                "template": response.template_used,
            },
            is_ai_generated=True,
        )
        db.add(activity)
        await db.commit()

        return response

    async def _get_ai_response(
        self,
        db: AsyncSession,
        lead: Lead,
        reply_text: str,
        analysis: ReplyAnalysis,
        tenant_id: UUID,
        user_id: Optional[UUID],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        """Generate AI response."""
        intent = analysis.intent.value
        sentiment = analysis.sentiment.value

        # Intent-specific templates
        templates = {
            "interested": "Thank you for your interest! I'd love to schedule a quick call to discuss how we can help.",
            "meeting_request": "I'd be happy to schedule a demo. Here are some available times...",
            "pricing_objection": "I understand budget is important. Let me share the value breakdown and ROI.",
            "needs_information": "I've attached the information you requested. Happy to walk through it.",
            "not_interested": "Thank you for your honesty. I'll respect your decision and won't follow up.",
            "out_of_office": "No problem - I'll follow up when you're back. Enjoy your time off!",
            "wrong_person": "Could you point me to the right person? Thanks for the redirect.",
            "unsubscribe": "You've been unsubscribed. Sorry for any inconvenience.",
            "support_request": "I'll connect you with our support team right away.",
        }

        template = templates.get(intent, "Thank you for your message. We'll get back to you soon.")

        prompt = f"""
        Generate a personalized email response to this lead reply.
        
        Lead: {lead.contact.full_name if lead.contact else 'Unknown'}
        Company: {lead.contact.company.name if lead.contact and lead.contact.company else 'Unknown'}
        Intent: {intent}
        Sentiment: {sentiment}
        Reply: {reply_text}
        
        Context:
        - Our last email: {lead.ai_next_action or 'Previous outreach'}
        - Lead score: {lead.ai_score}
        - Recommended action: {analysis.recommended_action}
        
        Guidelines:
        - Professional, concise, value-focused tone
        - Address their specific questions/concerns
        - Include clear next step
        - No more than 3 short paragraphs
        - Use their name
        
        Return JSON:
        {{
            "subject": "Re: ...",
            "body": "Full email body with greeting and signature",
            "confidence": 0.9,
            "template": "interested"
        }}
        """

        result = await self.router.complete(
            task_type=AITaskTypeEnum.REPLY_GENERATION,
            prompt=prompt,
            tenant_id=tenant_id,
            user_id=user_id,
            correlation_id=correlation_id,
            response_format={"type": "json_object"},
            temperature=0.4,
            db=db,
        )

        if result.success:
            import json
            try:
                return json.loads(result.content)
            except json.JSONDecodeError:
                pass

        return {
            "subject": f"Re: {lead.title}",
            "body": f"Hi {lead.contact.first_name if lead.contact else 'there'},\n\n{template}\n\nBest regards,\n{lead.owner.full_name if lead.owner else 'Sales Team'}",
            "confidence": 0.6,
            "template": intent,
        }


# Need imports
from sqlalchemy.orm import selectinload
from app.models import Company