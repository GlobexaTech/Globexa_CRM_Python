from app.models import Contact
"""
AI Auto-Assignment Service for Globexa CRM.
Hybrid rule-based + AI assignment with explainable reasoning.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import User, Membership, Lead, RoleEnum
from app.services.ai.router import get_ai_router, AITaskTypeEnum

logger = structlog.get_logger()


@dataclass
class AssignmentFactor:
    """Assignment scoring factor."""
    name: str
    weight: float
    score: float  # 0-1 for this salesperson
    evidence: str


@dataclass
class AssignmentResult:
    """Assignment decision result."""
    lead_id: UUID
    assigned_user_id: UUID
    assigned_user_name: str
    confidence: float
    reasoning: str
    factors: List[AssignmentFactor]
    alternative_candidates: List[Dict[str, Any]]
    model_version: str
    assigned_at: datetime


class AssignmentRule:
    """Configurable assignment rule."""
    def __init__(self, config: Dict[str, Any]):
        self.industry_expertise_weight = config.get("industry_expertise_weight", 0.25)
        self.territory_weight = config.get("territory_weight", 0.20)
        self.language_weight = config.get("language_weight", 0.10)
        self.specialization_weight = config.get("specialization_weight", 0.15)
        self.workload_weight = config.get("workload_weight", 0.15)
        self.conversion_rate_weight = config.get("conversion_rate_weight", 0.10)
        self.lead_score_weight = config.get("lead_score_weight", 0.05)
        self.deal_value_weight = config.get("deal_value_weight", 0.05)
        self.availability_weight = config.get("availability_weight", 0.05)
        self.relationship_weight = config.get("relationship_weight", 0.05)


class AutoAssignmentService:
    """AI-powered lead assignment with rule-based + AI hybrid."""

    def __init__(self):
        self.router = get_ai_router()
        self.default_rules = AssignmentRule({})

    async def assign_lead(
        self,
        db: AsyncSession,
        lead_id: UUID,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,  # User requesting assignment
        correlation_id: Optional[str] = None,
        override_rules: Optional[Dict[str, Any]] = None,
    ) -> AssignmentResult:
        """Assign a lead to the best salesperson."""
        # Load lead
        result = await db.execute(
            select(Lead)
            .where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
            .options(selectinload(Lead.contact).selectinload(Contact.company))
        )
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Get eligible salespeople
        salespeople = await self._get_eligible_salespeople(db, tenant_id, lead)
        if not salespeople:
            raise ValueError("No eligible salespeople available for assignment")

        # Calculate scores for each salesperson
        scored_candidates = []
        rules = AssignmentRule(override_rules) if override_rules else self.default_rules

        for sp in salespeople:
            factors = await self._calculate_assignment_factors(db, sp, lead, tenant_id, rules)
            total_score = sum(f.score * f.weight for f in factors)
            total_weight = sum(f.weight for f in factors)
            weighted_score = total_score / total_weight if total_weight > 0 else 0
            
            scored_candidates.append({
                "user": sp,
                "score": weighted_score,
                "factors": factors,
            })

        # Sort by score descending
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        # Get AI recommendation for top candidates
        top_candidates = scored_candidates[:3]
        ai_recommendation = await self._get_ai_recommendation(db, lead, top_candidates, tenant_id, user_id, correlation_id)

        # Combine rule-based and AI
        best_candidate = scored_candidates[0]
        final_score = 0.7 * best_candidate["score"] + 0.3 * ai_recommendation.get("score", best_candidate["score"])
        
        # Apply AI reasoning
        reasoning = ai_recommendation.get("reasoning", "")
        if not reasoning:
            top_factors = [f.name for f in best_candidate["factors"] if f.score > 0.7]
            reasoning = f"Best match based on: {', '.join(top_factors[:3])}"

        # Assign lead
        assigned_user = best_candidate["user"]
        lead.owner_id = assigned_user.id
        lead.assigned_by_id = user_id
        lead.assigned_at = datetime.now(timezone.utc)
        lead.updated_at = datetime.now(timezone.utc)

        # Create activity
        from app.models import Activity, ActivityTypeEnum
        activity = Activity(
            tenant_id=tenant_id,
            lead_id=lead_id,
            type=ActivityTypeEnum.ASSIGNMENT,
            subject=f"Lead assigned to {assigned_user.full_name}",
            description=f"Auto-assigned: {reasoning}",
            user_id=user_id,
            metadata={"assignment_factors": [f.name for f in best_candidate["factors"]]},
        )
        db.add(activity)

        await db.commit()

        return AssignmentResult(
            lead_id=lead_id,
            assigned_user_id=assigned_user.id,
            assigned_user_name=assigned_user.full_name,
            confidence=min(final_score, 1.0),
            reasoning=reasoning,
            factors=best_candidate["factors"],
            alternative_candidates=[{
                "user_id": str(c["user"].id),
                "name": c["user"].full_name,
                "score": c["score"],
            } for c in scored_candidates[1:4]],
            model_version="v1.0",
            assigned_at=datetime.now(timezone.utc),
        )

    async def _get_eligible_salespeople(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        lead: Lead,
    ) -> List[User]:
        """Get salespeople eligible for lead assignment."""
        # Get all active sales executives and managers in tenant
        result = await db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.role.in_([RoleEnum.SALES_EXECUTIVE, RoleEnum.SALES_MANAGER]),
                User.is_active == True,
            )
            .options(selectinload(User.memberships))
        )
        users = result.scalars().all()

        # Filter by workload capacity (configurable)
        eligible = []
        for user in users:
            membership = next((m for m in user.memberships if m.tenant_id == tenant_id), None)
            if membership and membership.role in [RoleEnum.SALES_EXECUTIVE, RoleEnum.SALES_MANAGER]:
                # Check current lead count
                lead_count_result = await db.execute(
                    select(func.count()).select_from(Lead).where(
                        Lead.tenant_id == tenant_id,
                        Lead.owner_id == user.id,
                        Lead.status.in_(["new", "contacted", "qualified", "nurturing"]),
                    )
                )
                active_leads = lead_count_result.scalar() or 0
                
                # Max leads per salesperson (configurable per tenant)
                max_leads = 50  # Could be from tenant settings
                if active_leads < max_leads:
                    eligible.append(user)

        return eligible

    async def _calculate_assignment_factors(
        self,
        db: AsyncSession,
        salesperson: User,
        lead: Lead,
        tenant_id: UUID,
        rules: AssignmentRule,
    ) -> List[AssignmentFactor]:
        """Calculate assignment factors for a salesperson."""
        factors = []
        membership = next((m for m in salesperson.memberships if m.tenant_id == tenant_id), None)

        # 1. Industry Expertise
        industry_score = await self._calculate_industry_expertise(db, salesperson, lead, tenant_id)
        factors.append(AssignmentFactor(
            name="Industry Expertise",
            weight=rules.industry_expertise_weight,
            score=industry_score,
            evidence=f"Industry: {lead.company.industry if lead.company else 'Unknown'}",
        ))

        # 2. Territory/Geography
        territory_score = await self._calculate_territory_match(db, salesperson, lead, tenant_id)
        factors.append(AssignmentFactor(
            name="Territory Match",
            weight=rules.territory_weight,
            score=territory_score,
            evidence=f"Lead location: {lead.company.city if lead.company else 'Unknown'}",
        ))

        # 3. Language
        language_score = await self._calculate_language_match(db, salesperson, lead, tenant_id)
        factors.append(AssignmentFactor(
            name="Language Match",
            weight=rules.language_weight,
            score=language_score,
            evidence="Language compatibility",
        ))

        # 4. Specialization
        specialization_score = await self._calculate_specialization(db, salesperson, lead, tenant_id)
        factors.append(AssignmentFactor(
            name="Service Specialization",
            weight=rules.specialization_weight,
            score=specialization_score,
            evidence=f"Service: {lead.custom_fields.get('service_interest', 'Unknown') if lead.custom_fields else 'Unknown'}",
        ))

        # 5. Current Workload
        workload_score = await self._calculate_workload(db, salesperson, tenant_id)
        factors.append(AssignmentFactor(
            name="Current Workload",
            weight=rules.workload_weight,
            score=workload_score,
            evidence=f"Active leads: {await self._get_active_lead_count(db, salesperson, tenant_id)}",
        ))

        # 6. Historical Conversion Rate
        conversion_score = await self._calculate_conversion_rate(db, salesperson, tenant_id)
        factors.append(AssignmentFactor(
            name="Conversion Rate",
            weight=rules.conversion_rate_weight,
            score=conversion_score,
            evidence="Historical performance",
        ))

        # 7. Lead Score Match
        lead_score = lead.ai_score or 50
        lead_score_factor = min(1.0, lead_score / 100)
        factors.append(AssignmentFactor(
            name="Lead Score Match",
            weight=rules.lead_score_weight,
            score=lead_score_factor,
            evidence=f"AI Score: {lead_score}",
        ))

        # 8. Estimated Deal Value
        deal_value = lead.custom_fields.get("estimated_value", 0) if lead.custom_fields else 0
        value_factor = min(1.0, deal_value / 100000) if deal_value else 0.5
        factors.append(AssignmentFactor(
            name="Deal Value",
            weight=rules.deal_value_weight,
            score=value_factor,
            evidence=f"Estimated value: ${deal_value:,.0f}" if deal_value else "Unknown",
        ))

        # 9. Availability
        availability_score = 1.0  # Simplified - could check calendar
        factors.append(AssignmentFactor(
            name="Availability",
            weight=rules.availability_weight,
            score=availability_score,
            evidence="Available for new leads",
        ))

        # 10. Existing Relationship
        relationship_score = await self._calculate_relationship(db, salesperson, lead, tenant_id)
        factors.append(AssignmentFactor(
            name="Existing Relationship",
            weight=rules.relationship_weight,
            score=relationship_score,
            evidence="Previous interactions" if relationship_score > 0 else "No prior relationship",
        ))

        return factors

    async def _calculate_industry_expertise(
        self, db: AsyncSession, salesperson: User, lead: Lead, tenant_id: UUID
    ) -> float:
        """Calculate industry expertise score (0-1)."""
        if not lead.company or not lead.company.industry:
            return 0.5

        # Check past deals in same industry
        result = await db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.owner_id == salesperson.id,
                Lead.company.has(Company.industry == lead.company.industry),
                Lead.status.in_(["converted", "qualified"]),
            )
        )
        industry_deals = result.scalar() or 0

        total_result = await db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.owner_id == salesperson.id,
                Lead.status.in_(["converted", "qualified"]),
            )
        )
        total_deals = total_result.scalar() or 1

        if total_deals == 0:
            return 0.5  # No history, neutral

        industry_ratio = industry_deals / total_deals
        # If >30% deals in this industry, high expertise
        return min(1.0, industry_ratio * 3)

    async def _calculate_territory_match(
        self, db: AsyncSession, salesperson: User, lead: Lead, tenant_id: UUID
    ) -> float:
        """Calculate territory match score (0-1)."""
        # Check salesperson's territory (from custom fields or user profile)
        territory = salesperson.custom_fields.get("territory") if salesperson.custom_fields else None
        lead_city = lead.company.city if lead.company else None
        lead_state = lead.company.state if lead.company else None
        lead_country = lead.company.country if lead.company else None

        if not territory:
            return 0.5

        if lead_country and territory.get("countries") and lead_country in territory["countries"]:
            return 1.0
        if lead_state and territory.get("states") and lead_state in territory["states"]:
            return 0.8
        if lead_city and territory.get("cities") and lead_city in territory["cities"]:
            return 1.0

        return 0.3  # Partial match

    async def _calculate_language_match(
        self, db: AsyncSession, salesperson: User, lead: Lead, tenant_id: UUID
    ) -> float:
        """Calculate language match score (0-1)."""
        languages = salesperson.custom_fields.get("languages") if salesperson.custom_fields else []
        if not languages:
            return 0.5

        lead_country = lead.company.country if lead.company else None
        # Simple mapping - in production use proper language detection
        country_language = {
            "US": "English", "UK": "English", "CA": "English", "AU": "English",
            "ES": "Spanish", "MX": "Spanish", "AR": "Spanish", "CO": "Spanish",
            "FR": "French", "DE": "German", "IT": "Italian", "PT": "Portuguese",
            "BR": "Portuguese", "JP": "Japanese", "CN": "Chinese",
        }
        needed_lang = country_language.get(lead_country, "English")
        
        return 1.0 if needed_lang in languages else 0.3

    async def _calculate_specialization(
        self, db: AsyncSession, salesperson: User, lead: Lead, tenant_id: UUID
    ) -> float:
        """Calculate service specialization score (0-1)."""
        specializations = salesperson.custom_fields.get("specializations") if salesperson.custom_fields else []
        if not specializations:
            return 0.5

        service_interest = lead.custom_fields.get("service_interest") if lead.custom_fields else None
        if not service_interest:
            return 0.5

        return 1.0 if service_interest in specializations else 0.3

    async def _calculate_workload(
        self, db: AsyncSession, salesperson: User, tenant_id: UUID
    ) -> float:
        """Calculate workload score (0-1, higher = more capacity)."""
        active_count = await self._get_active_lead_count(db, salesperson, tenant_id)
        max_leads = 50  # Configurable
        
        if active_count >= max_leads:
            return 0.0
        elif active_count >= max_leads * 0.8:
            return 0.3
        elif active_count >= max_leads * 0.5:
            return 0.6
        else:
            return 1.0

    async def _get_active_lead_count(
        self, db: AsyncSession, salesperson: User, tenant_id: UUID
    ) -> int:
        """Get count of active leads for salesperson."""
        result = await db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.owner_id == salesperson.id,
                Lead.status.in_(["new", "contacted", "qualified", "nurturing"]),
            )
        )
        return result.scalar() or 0

    async def _calculate_conversion_rate(
        self, db: AsyncSession, salesperson: User, tenant_id: UUID
    ) -> float:
        """Calculate historical conversion rate (0-1)."""
        result = await db.execute(
            select(
                func.count().filter(Lead.status == "converted").label("won"),
                func.count().label("total"),
            ).where(
                Lead.tenant_id == tenant_id,
                Lead.owner_id == salesperson.id,
                Lead.status.in_(["converted", "lost", "qualified"]),
            )
        )
        row = result.first()
        if row and row.total > 0:
            return row.won / row.total
        return 0.5

    async def _calculate_relationship(
        self, db: AsyncSession, salesperson: User, lead: Lead, tenant_id: UUID
    ) -> float:
        """Check if salesperson has existing relationship with lead/contact."""
        if not lead.contact:
            return 0.0

        # Check past activities
        result = await db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.owner_id == salesperson.id,
                Lead.contact_id == lead.contact_id,
            )
        )
        past_leads = result.scalar() or 0

        if past_leads > 0:
            return min(1.0, past_leads * 0.3)
        return 0.0

    async def _get_ai_recommendation(
        self,
        db: AsyncSession,
        lead: Lead,
        top_candidates: List[Dict],
        tenant_id: UUID,
        user_id: Optional[UUID],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        """Get AI recommendation for assignment."""
        candidates_info = "\n".join([
            f"- {c['user'].full_name}: Score {c['score']:.2f}, Factors: {', '.join([f.name for f in c['factors'] if f.score > 0.7])}"
            for c in top_candidates
        ])

        prompt = f"""
        Recommend the best salesperson for this lead:
        
        Lead: {lead.title}
        Company: {lead.company.name if lead.company else 'Unknown'}
        Industry: {lead.company.industry if lead.company else 'Unknown'}
        AI Score: {lead.ai_score or 'Not scored'}
        Source: {lead.source.value if lead.source else 'Unknown'}
        
        Top Candidates:
        {candidates_info}
        
        Consider: Industry expertise, territory, workload, conversion history, relationship.
        
        Return JSON:
        {{
            "recommended_user_id": "uuid",
            "score": 0.92,
            "reasoning": "Best match because...",
            "confidence": 0.85
        }}
        """

        result = await self.router.complete(
            task_type=AITaskTypeEnum.ROUTING_DECISION,
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

        # Fallback to top rule-based candidate
        return {
            "recommended_user_id": str(top_candidates[0]["user"].id),
            "score": top_candidates[0]["score"],
            "reasoning": "Rule-based top candidate",
            "confidence": 0.7,
        }

# Need to import selectinload and Company
from sqlalchemy.orm import selectinload
from app.models import Company