"""
AI Lead Scoring Service for Globexa CRM.
Provides explainable lead scoring with factor breakdown.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import Lead, Contact, Company, Activity, ActivityTypeEnum
from app.services.ai.router import get_ai_router, AITaskTypeEnum

logger = structlog.get_logger()


@dataclass
class ScoringFactor:
    """Individual scoring factor."""
    name: str
    weight: float
    score: int  # 0-100
    evidence: str
    category: str  # demographic, firmographic, behavioral, engagement


@dataclass
class LeadScoreResult:
    """Complete lead scoring result."""
    lead_id: UUID
    score: int  # 0-100
    confidence: float  # 0-1
    factors: List[ScoringFactor]
    reasoning: str
    recommended_action: str
    model_version: str
    scored_at: datetime


class LeadScoringService:
    """AI-powered lead scoring with explainable results."""

    # Scoring weights (can be configured per tenant)
    DEFAULT_WEIGHTS = {
        "demographic": 0.20,      # Title, role, seniority
        "firmographic": 0.25,     # Company size, industry, revenue
        "behavioral": 0.30,       # Website visits, content downloads, email engagement
        "engagement": 0.25,       # Email opens, clicks, replies, meeting attendance
    }

    # Factor definitions
    DEMOGRAPHIC_FACTORS = {
        "decision_maker_title": {"weight": 0.4, "keywords": ["ceo", "cto", "vp", "director", "head of", "founder", "owner"]},
        "seniority_level": {"weight": 0.3, "keywords": ["senior", "lead", "principal", "manager", "director"]},
        "relevant_department": {"weight": 0.3, "keywords": ["sales", "marketing", "growth", "revenue", "business development"]},
    }

    FIRMOGRAPHIC_FACTORS = {
        "company_size_match": {"weight": 0.35, "ideal_range": (10, 500)},
        "industry_fit": {"weight": 0.35, "target_industries": ["saas", "technology", "professional services", "finance", "healthcare"]},
        "revenue_potential": {"weight": 0.3, "min_revenue": 1000000},
    }

    BEHAVIORAL_FACTORS = {
        "website_visits": {"weight": 0.25, "thresholds": [(10, 100), (5, 70), (2, 40), (1, 20)]},
        "content_downloads": {"weight": 0.25, "thresholds": [(5, 100), (3, 70), (1, 40)]},
        "pricing_page_views": {"weight": 0.3, "thresholds": [(3, 100), (1, 50)]},
        "demo_requests": {"weight": 0.2, "thresholds": [(1, 100)]},
    }

    ENGAGEMENT_FACTORS = {
        "email_open_rate": {"weight": 0.3, "thresholds": [(0.5, 100), (0.3, 70), (0.15, 40)]},
        "email_click_rate": {"weight": 0.3, "thresholds": [(0.1, 100), (0.05, 70), (0.02, 40)]},
        "email_replies": {"weight": 0.25, "thresholds": [(2, 100), (1, 70)]},
        "meeting_attendance": {"weight": 0.15, "thresholds": [(1, 100)]},
    }

    def __init__(self):
        self.router = get_ai_router()

    async def score_lead(
        self,
        db: AsyncSession,
        lead_id: UUID,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> LeadScoreResult:
        """Score a lead with explainable factors."""
        # Load lead with relations
        result = await db.execute(
            select(Lead)
            .where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
            .options(
                selectinload(Lead.contact).selectinload(Contact.company),
                selectinload(Lead.company),
            )
        )
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Gather data for scoring
        scoring_data = await self._gather_scoring_data(db, lead, tenant_id)

        # Calculate rule-based scores
        factors = self._calculate_rule_based_factors(scoring_data)

        # Get AI-enhanced scoring
        ai_result = await self._get_ai_scoring(db, lead, scoring_data, tenant_id, user_id, correlation_id)

        # Combine scores
        final_score, final_factors, reasoning = self._combine_scores(factors, ai_result)

        # Determine recommended action
        recommended_action = self._get_recommended_action(final_score, scoring_data)

        # Save score to lead
        lead.ai_score = final_score
        lead.ai_score_reason = reasoning
        lead.ai_next_action = recommended_action
        lead.ai_next_action_confidence = ai_result.get("confidence", 0.8)
        await db.commit()

        return LeadScoreResult(
            lead_id=lead_id,
            score=final_score,
            confidence=ai_result.get("confidence", 0.8),
            factors=final_factors,
            reasoning=reasoning,
            recommended_action=recommended_action,
            model_version="v1.0",
            scored_at=datetime.now(timezone.utc),
        )

    async def _gather_scoring_data(
        self,
        db: AsyncSession,
        lead: Lead,
        tenant_id: UUID,
    ) -> Dict[str, Any]:
        """Gather all data needed for scoring."""
        contact = lead.contact
        company = lead.company or (contact.company if contact else None)

        # Get activities for engagement metrics
        activities_result = await db.execute(
            select(Activity)
            .where(
                Activity.tenant_id == tenant_id,
                Activity.lead_id == lead.id,
            )
            .order_by(Activity.created_at.desc())
        )
        activities = activities_result.scalars().all()

        # Calculate engagement metrics
        email_activities = [a for a in activities if a.type in [
            ActivityTypeEnum.EMAIL_OPENED,
            ActivityTypeEnum.EMAIL_CLICKED,
            ActivityTypeEnum.EMAIL_REPLIED,
            ActivityTypeEnum.EMAIL,
        ]]

        total_emails = len([a for a in activities if a.type == ActivityTypeEnum.EMAIL])
        total_opens = len([a for a in email_activities if a.type == ActivityTypeEnum.EMAIL_OPENED])
        total_clicks = len([a for a in email_activities if a.type == ActivityTypeEnum.EMAIL_CLICKED])
        total_replies = len([a for a in email_activities if a.type == ActivityTypeEnum.EMAIL_REPLIED])
        meetings = len([a for a in activities if a.type == ActivityTypeEnum.MEETING])

        # Website/behavioral data (from custom fields or tracking)
        behavioral = lead.custom_fields.get("behavioral", {}) if lead.custom_fields else {}

        return {
            "lead": {
                "id": str(lead.id),
                "title": lead.title,
                "status": lead.status.value,
                "source": lead.source.value if lead.source else None,
                "ai_score": lead.ai_score,
                "custom_fields": lead.custom_fields,
            },
            "contact": {
                "id": str(contact.id) if contact else None,
                "first_name": contact.first_name if contact else None,
                "last_name": contact.last_name if contact else None,
                "title": contact.title if contact else None,
                "email": contact.email if contact else None,
                "company_id": str(contact.company_id) if contact and contact.company_id else None,
            } if contact else None,
            "company": {
                "id": str(company.id) if company else None,
                "name": company.name if company else None,
                "domain": company.domain if company else None,
                "industry": company.industry if company else None,
                "size": company.size if company else None,
                "annual_revenue": company.annual_revenue if company else None,
                "custom_fields": company.custom_fields if company else None,
            } if company else None,
            "engagement": {
                "total_emails_sent": total_emails,
                "total_opens": total_opens,
                "total_clicks": total_clicks,
                "total_replies": total_replies,
                "meetings": meetings,
                "open_rate": total_opens / total_emails if total_emails > 0 else 0,
                "click_rate": total_clicks / total_emails if total_emails > 0 else 0,
                "reply_rate": total_replies / total_emails if total_emails > 0 else 0,
            },
            "behavioral": behavioral,
        }

    def _calculate_rule_based_factors(self, data: Dict[str, Any]) -> List[ScoringFactor]:
        """Calculate scores using rule-based factors."""
        factors = []
        contact = data.get("contact") or {}
        company = data.get("company") or {}
        engagement = data.get("engagement") or {}
        behavioral = data.get("behavioral") or {}

        # Demographic factors
        title = (contact.get("title") or "").lower()
        if any(kw in title for kw in self.DEMOGRAPHIC_FACTORS["decision_maker_title"]["keywords"]):
            factors.append(ScoringFactor(
                name="Decision Maker Title",
                weight=self.DEMOGRAPHIC_FACTORS["decision_maker_title"]["weight"],
                score=90,
                evidence=f"Title: {contact.get('title', 'N/A')}",
                category="demographic",
            ))
        elif any(kw in title for kw in self.DEMOGRAPHIC_FACTORS["seniority_level"]["keywords"]):
            factors.append(ScoringFactor(
                name="Seniority Level",
                weight=self.DEMOGRAPHIC_FACTORS["seniority_level"]["weight"],
                score=70,
                evidence=f"Title: {contact.get('title', 'N/A')}",
                category="demographic",
            ))
        elif any(kw in title for kw in self.DEMOGRAPHIC_FACTORS["relevant_department"]["keywords"]):
            factors.append(ScoringFactor(
                name="Relevant Department",
                weight=self.DEMOGRAPHIC_FACTORS["relevant_department"]["weight"],
                score=60,
                evidence=f"Title: {contact.get('title', 'N/A')}",
                category="demographic",
            ))

        # Firmographic factors
        if company:
            size = company.get("size", "")
            industry = (company.get("industry") or "").lower()
            revenue = company.get("annual_revenue", 0)

            # Company size
            try:
                if "-" in size:
                    min_size, max_size = map(int, size.replace("+", "").split("-"))
                    avg_size = (min_size + max_size) / 2
                else:
                    avg_size = int(size.replace("+", ""))
                
                ideal_min, ideal_max = self.FIRMOGRAPHIC_FACTORS["company_size_match"]["ideal_range"]
                if ideal_min <= avg_size <= ideal_max:
                    size_score = 100
                elif avg_size < ideal_min:
                    size_score = max(30, 100 - (ideal_min - avg_size) * 2)
                else:
                    size_score = max(30, 100 - (avg_size - ideal_max) / 10)
                
                factors.append(ScoringFactor(
                    name="Company Size Fit",
                    weight=self.FIRMOGRAPHIC_FACTORS["company_size_match"]["weight"],
                    score=size_score,
                    evidence=f"Company size: {size} employees",
                    category="firmographic",
                ))
            except (ValueError, TypeError):
                logger.debug("Company size is not numeric")

            # Industry fit
            target_industries = self.FIRMOGRAPHIC_FACTORS["industry_fit"]["target_industries"]
            if any(ti in industry for ti in target_industries):
                industry_score = 90
            else:
                industry_score = 40
            
            factors.append(ScoringFactor(
                name="Industry Fit",
                weight=self.FIRMOGRAPHIC_FACTORS["industry_fit"]["weight"],
                score=industry_score,
                evidence=f"Industry: {company.get('industry', 'N/A')}",
                category="firmographic",
            ))

            # Revenue potential
            min_rev = self.FIRMOGRAPHIC_FACTORS["revenue_potential"]["min_revenue"]
            if revenue >= min_rev:
                rev_score = min(100, 50 + int(revenue / min_rev * 25))
            else:
                rev_score = max(20, int(revenue / min_rev * 50))
            
            factors.append(ScoringFactor(
                name="Revenue Potential",
                weight=self.FIRMOGRAPHIC_FACTORS["revenue_potential"]["weight"],
                score=rev_score,
                evidence=f"Annual revenue: ${revenue:,.0f}" if revenue else "Revenue unknown",
                category="firmographic",
            ))

        # Behavioral factors
        website_visits = behavioral.get("website_visits", 0)
        for threshold, score in self.BEHAVIORAL_FACTORS["website_visits"]["thresholds"]:
            if website_visits >= threshold:
                factors.append(ScoringFactor(
                    name="Website Visits",
                    weight=self.BEHAVIORAL_FACTORS["website_visits"]["weight"],
                    score=score,
                    evidence=f"{website_visits} website visits",
                    category="behavioral",
                ))
                break

        pricing_views = behavioral.get("pricing_page_views", 0)
        for threshold, score in self.BEHAVIORAL_FACTORS["pricing_page_views"]["thresholds"]:
            if pricing_views >= threshold:
                factors.append(ScoringFactor(
                    name="Pricing Page Views",
                    weight=self.BEHAVIORAL_FACTORS["pricing_page_views"]["weight"],
                    score=score,
                    evidence=f"{pricing_views} pricing page views",
                    category="behavioral",
                ))
                break

        # Engagement factors
        open_rate = engagement.get("open_rate", 0)
        for threshold, score in self.ENGAGEMENT_FACTORS["email_open_rate"]["thresholds"]:
            if open_rate >= threshold:
                factors.append(ScoringFactor(
                    name="Email Open Rate",
                    weight=self.ENGAGEMENT_FACTORS["email_open_rate"]["weight"],
                    score=score,
                    evidence=f"{open_rate:.0%} open rate ({engagement.get('total_opens', 0)}/{engagement.get('total_emails_sent', 0)})",
                    category="engagement",
                ))
                break

        click_rate = engagement.get("click_rate", 0)
        for threshold, score in self.ENGAGEMENT_FACTORS["email_click_rate"]["thresholds"]:
            if click_rate >= threshold:
                factors.append(ScoringFactor(
                    name="Email Click Rate",
                    weight=self.ENGAGEMENT_FACTORS["email_click_rate"]["weight"],
                    score=score,
                    evidence=f"{click_rate:.1%} click rate ({engagement.get('total_clicks', 0)}/{engagement.get('total_emails_sent', 0)})",
                    category="engagement",
                ))
                break

        replies = engagement.get("total_replies", 0)
        for threshold, score in self.ENGAGEMENT_FACTORS["email_replies"]["thresholds"]:
            if replies >= threshold:
                factors.append(ScoringFactor(
                    name="Email Replies",
                    weight=self.ENGAGEMENT_FACTORS["email_replies"]["weight"],
                    score=score,
                    evidence=f"{replies} email replies",
                    category="engagement",
                ))
                break

        return factors

    async def _get_ai_scoring(
        self,
        db: AsyncSession,
        lead: Lead,
        data: Dict[str, Any],
        tenant_id: UUID,
        user_id: Optional[UUID],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        """Get AI-enhanced scoring."""
        prompt = f"""
        Analyze this lead and provide a score (0-100) with confidence and key factors.
        
        Lead: {lead.title}
        Status: {lead.status.value}
        Source: {lead.source.value if lead.source else 'unknown'}
        
        Contact: {data.get('contact')}
        Company: {data.get('company')}
        Engagement: {data.get('engagement')}
        Behavioral: {data.get('behavioral')}
        
        Consider: ICP fit, buying signals, engagement quality, decision authority, budget indicators, timeline urgency.
        
        Return JSON:
        {{
            "score": 85,
            "confidence": 0.92,
            "key_factors": [
                {{"factor": "Decision maker title", "impact": "high", "evidence": "CTO title"}},
                {{"factor": "High engagement", "impact": "medium", "evidence": "3 email replies, 2 meetings"}}
            ],
            "risk_factors": ["Long sales cycle expected", "Competitor evaluation"],
            "recommended_action": "Schedule demo within 48 hours",
            "timeline": "within_week"
        }}
        """

        result = await self.router.complete(
            task_type=AITaskTypeEnum.LEAD_SCORING,
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

        return {"score": 50, "confidence": 0.5, "key_factors": [], "recommended_action": "Review manually"}

    def _combine_scores(
        self,
        rule_factors: List[ScoringFactor],
        ai_result: Dict[str, Any],
    ) -> tuple[int, List[ScoringFactor], str]:
        """Combine rule-based and AI scores."""
        # Calculate weighted rule-based score
        if rule_factors:
            total_weight = sum(f.weight for f in rule_factors)
            rule_score = sum(f.score * f.weight for f in rule_factors) / total_weight if total_weight > 0 else 50
        else:
            rule_score = 50

        ai_score = ai_result.get("score", 50)
        ai_confidence = ai_result.get("confidence", 0.5)

        # Weighted combination: 60% rules, 40% AI (adjustable)
        final_score = int(0.6 * rule_score + 0.4 * ai_score)

        # Merge factors
        all_factors = list(rule_factors)
        for kf in ai_result.get("key_factors", []):
            all_factors.append(ScoringFactor(
                name=kf.get("factor", "AI Factor"),
                weight=0.1,
                score=int(kf.get("impact_score", 70)),
                evidence=kf.get("evidence", ""),
                category="ai_enhanced",
            ))

        reasoning = ai_result.get("reasoning", "Combined rule-based and AI analysis")
        if not reasoning:
            key_factors = [f.name for f in all_factors if f.score >= 70]
            reasoning = f"Strong signals: {', '.join(key_factors[:3])}" if key_factors else "Moderate lead quality"

        return final_score, all_factors, reasoning

    def _get_recommended_action(self, score: int, data: Dict[str, Any]) -> str:
        """Determine recommended action based on score and context."""
        engagement = data.get("engagement", {})
        replies = engagement.get("total_replies", 0)
        meetings = engagement.get("meetings", 0)

        if score >= 85:
            if replies > 0 or meetings > 0:
                return "Close deal - send proposal and negotiate"
            return "Schedule demo within 24 hours"
        elif score >= 70:
            if replies > 0:
                return "Schedule demo and send case study"
            return "Call within 4 hours with personalized outreach"
        elif score >= 50:
            return "Add to nurture sequence, send educational content"
        elif score >= 30:
            return "Low priority - monitor for engagement signals"
        else:
            return "Disqualify or long-term nurture"


# Need to import selectinload
from sqlalchemy.orm import selectinload