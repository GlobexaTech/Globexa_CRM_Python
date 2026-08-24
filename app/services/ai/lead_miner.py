"""
AI Lead Miner Service for Globexa CRM.
Discovers and enriches prospects based on Ideal Customer Profile (ICP).
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import structlog
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import Tenant, User, Company, Contact, Lead, LeadSourceEnum
from app.services.ai.router import get_ai_router, AITaskTypeEnum

logger = structlog.get_logger()


@dataclass
class ICPDefinition:
    """Ideal Customer Profile definition."""
    name: str
    description: str
    industries: List[str]
    company_size_range: tuple[int, int]  # (min, max) employees
    geographies: List[str]  # Countries/states
    technologies: List[str]  # Tech stack signals
    keywords: List[str]  # Business keywords
    exclude_industries: List[str]
    exclude_keywords: List[str]
    min_revenue: Optional[int] = None  # Annual revenue in USD
    max_revenue: Optional[int] = None
    funding_stage: Optional[List[str]] = None
    employee_growth_rate: Optional[float] = None


@dataclass
class DiscoveredProspect:
    """Discovered prospect from Lead Miner."""
    company_name: str
    domain: Optional[str]
    website: Optional[str]
    founder_name: Optional[str]
    founder_linkedin: Optional[str]
    founder_email: Optional[str]
    phone: Optional[str]
    location: Optional[str]
    company_size: Optional[str]
    industry: Optional[str]
    annual_revenue: Optional[int]
    technologies: List[str]
    advertising_signals: List[str]
    funding_info: Optional[Dict[str, Any]]
    employee_growth: Optional[float]
    icp_score: int  # 0-100
    icp_reason: str
    recommended_pitch: str
    recommended_next_action: str
    confidence: float
    raw_data: Dict[str, Any]


@dataclass
class LeadMinerResult:
    """Lead Miner execution result."""
    icp_id: UUID
    prospects_found: int
    prospects_qualified: int  # Score >= 85
    prospects_created: int
    execution_time_seconds: float
    cost_usd: float


class LeadMinerService:
    """AI-powered lead mining for ICP-based prospecting."""

    def __init__(self):
        self.router = get_ai_router()

    async def run_lead_miner(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        icp_definition: ICPDefinition,
        user_id: UUID,
        max_prospects: int = 50,
        min_score_threshold: int = 85,
        correlation_id: Optional[str] = None,
    ) -> LeadMinerResult:
        """Run AI Lead Miner to discover prospects matching ICP."""
        start_time = datetime.now(timezone.utc)
        
        # Create ICP record
        from app.models import ICPProfile
        icp = ICPProfile(
            tenant_id=tenant_id,
            name=icp_definition.name,
            description=icp_definition.description,
            criteria=icp_definition.__dict__,
            min_score_threshold=min_score_threshold,
            created_by_id=user_id,
        )
        db.add(icp)
        await db.flush()

        # Search for companies (AI-powered)
        search_results = await self._search_companies(db, tenant_id, icp_definition, max_prospects, user_id, correlation_id)
        
        # Enrich and score each prospect
        qualified_prospects = []
        for prospect_data in search_results:
            enriched = await self._enrich_prospect(db, tenant_id, prospect_data, icp_definition, user_id, correlation_id)
            if enriched.icp_score >= min_score_threshold:
                qualified_prospects.append(enriched)

        # Create leads for qualified prospects
        created_count = 0
        for prospect in qualified_prospects:
            try:
                await self._create_lead_from_prospect(db, tenant_id, prospect, icp.id, user_id)
                created_count += 1
            except Exception as e:
                logger.error("Failed to create lead from prospect", error=str(e))

        # Update ICP stats
        icp.prospects_found = len(search_results)
        icp.prospects_qualified = len(qualified_prospects)
        icp.prospects_created = created_count
        icp.last_run_at = datetime.now(timezone.utc)
        
        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        await db.commit()

        return LeadMinerResult(
            icp_id=icp.id,
            prospects_found=len(search_results),
            prospects_qualified=len(qualified_prospects),
            prospects_created=created_count,
            execution_time_seconds=execution_time,
            cost_usd=0.0,  # Would track from AI usage
        )

    async def _search_companies(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        icp: ICPDefinition,
        max_results: int,
        user_id: UUID,
        correlation_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Search for companies matching ICP using AI."""
        prompt = f"""
        Generate a list of {max_results} companies that match this Ideal Customer Profile:
        
        ICP Definition:
        - Name: {icp.name}
        - Description: {icp.description}
        - Target Industries: {icp.industries}
        - Company Size Range: {icp.company_size_range[0]}-{icp.company_size_range[1]} employees
        - Geographies: {icp.geographies}
        - Technologies: {icp.technologies}
        - Keywords: {icp.keywords}
        - Exclude Industries: {icp.exclude_industries}
        - Exclude Keywords: {icp.exclude_keywords}
        - Min Revenue: ${icp.min_revenue or 'Any'}
        - Max Revenue: ${icp.max_revenue or 'Any'}
        - Funding Stage: {icp.funding_stage or 'Any'}
        
        Return JSON:
        {{
            "companies": [
                {{
                    "name": "Company Name",
                    "domain": "company.com",
                    "website": "https://company.com",
                    "industry": "SaaS",
                    "size": "51-200",
                    "location": "San Francisco, CA, USA",
                    "estimated_revenue": 5000000,
                    "technologies": ["React", "AWS", "PostgreSQL"],
                    "advertising_signals": ["Google Ads", "LinkedIn Ads"],
                    "funding_stage": "Series A",
                    "employee_growth_rate": 0.15,
                    "key_decision_makers": [
                        {{"name": "John Doe", "title": "CTO", "linkedin": "linkedin.com/in/johndoe"}}
                    ],
                    "why_match": "Matches ICP: SaaS, 100 employees, uses React/AWS, growing"
                }}
            ]
        }}
        """

        result = await self.router.complete(
            task_type=AITaskTypeEnum.LEAD_MINING,
            prompt=prompt,
            tenant_id=tenant_id,
            user_id=user_id,
            correlation_id=correlation_id,
            response_format={"type": "json_object"},
            temperature=0.4,
            db=db,
        )

        if result.success:
            try:
                data = json.loads(result.content)
                return data.get("companies", [])
            except json.JSONDecodeError:
                pass

        return []

    async def _enrich_prospect(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        prospect_data: Dict[str, Any],
        icp: ICPDefinition,
        user_id: UUID,
        correlation_id: Optional[str],
    ) -> DiscoveredProspect:
        """Enrich prospect with additional data and score against ICP."""
        prompt = f"""
        Enrich this prospect data and score against ICP:
        
        Prospect Data:
        {json.dumps(prospect_data, indent=2)}
        
        ICP Criteria:
        {json.dumps(icp.__dict__, indent=2, default=str)}
        
        Tasks:
        1. Verify and enrich company data (website, contact info, revenue, tech stack)
        2. Find key decision makers (founders, C-level, VPs)
        3. Find contact info (email, phone, LinkedIn) where lawfully available
        4. Identify advertising/technology signals
        5. Calculate ICP match score (0-100) with detailed reasoning
        6. Generate personalized pitch and recommended next action
        
        Return JSON:
        {{
            "company_name": "...",
            "domain": "...",
            "website": "...",
            "founder_name": "...",
            "founder_linkedin": "...",
            "founder_email": "...",
            "phone": "...",
            "location": "...",
            "company_size": "...",
            "industry": "...",
            "annual_revenue": 5000000,
            "technologies": [...],
            "advertising_signals": [...],
            "funding_info": {{"stage": "Series A", "amount": 5000000}},
            "employee_growth": 0.15,
            "icp_score": 92,
            "icp_reason": "Perfect match: SaaS, 150 employees, uses target tech stack, Series A funded, 20% growth",
            "recommended_pitch": "Focus on scaling engineering team...",
            "recommended_next_action": "Email CTO about engineering productivity",
            "confidence": 0.88,
            "raw_data": {{}}
        }}
        """

        result = await self.router.complete(
            task_type=AITaskTypeEnum.LEAD_MINING,
            prompt=prompt,
            tenant_id=tenant_id,
            user_id=user_id,
            correlation_id=correlation_id,
            response_format={"type": "json_object"},
            temperature=0.3,
            db=db,
        )

        if result.success:
            try:
                data = json.loads(result.content)
                return DiscoveredProspect(**data)
            except (json.JSONDecodeError, TypeError):
                pass

        # Fallback
        return DiscoveredProspect(
            company_name=prospect_data.get("name", "Unknown"),
            domain=prospect_data.get("domain"),
            website=prospect_data.get("website"),
            icp_score=50,
            icp_reason="Enrichment failed",
            recommended_pitch="General outreach",
            recommended_next_action="Manual review",
            confidence=0.3,
            raw_data=prospect_data,
        )

    async def _create_lead_from_prospect(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        prospect: DiscoveredProspect,
        icp_id: UUID,
        user_id: UUID,
    ):
        """Create lead, contact, and company from qualified prospect."""
        # Check if company exists
        company = None
        if prospect.domain:
            result = await db.execute(
                select(Company).where(Company.tenant_id == tenant_id, Company.domain == prospect.domain)
            )
            company = result.scalar_one_or_none()

        if not company:
            company = Company(
                tenant_id=tenant_id,
                name=prospect.company_name,
                domain=prospect.domain,
                website=prospect.website,
                industry=prospect.industry,
                size=prospect.company_size,
                annual_revenue=prospect.annual_revenue,
                city=prospect.location.split(",")[0].strip() if prospect.location else None,
                country=prospect.location.split(",")[-1].strip() if prospect.location else None,
                custom_fields={
                    "technologies": prospect.technologies,
                    "advertising_signals": prospect.advertising_signals,
                    "funding_info": prospect.funding_info,
                    "employee_growth": prospect.employee_growth,
                    "icp_score": prospect.icp_score,
                    "icp_reason": prospect.icp_reason,
                },
                source=LeadSourceEnum.AI_LEAD_MINER,
            )
            db.add(company)
            await db.flush()

        # Check if contact exists
        contact = None
        if prospect.founder_email:
            result = await db.execute(
                select(Contact).where(Contact.tenant_id == tenant_id, Contact.email == prospect.founder_email)
            )
            contact = result.scalar_one_or_none()

        if not contact:
            contact = Contact(
                tenant_id=tenant_id,
                company_id=company.id,
                first_name=prospect.founder_name.split(" ")[0] if prospect.founder_name else "Unknown",
                last_name=" ".join(prospect.founder_name.split(" ")[1:]) if prospect.founder_name and len(prospect.founder_name.split(" ")) > 1 else "Contact",
                email=prospect.founder_email,
                phone=prospect.phone,
                title=prospect.founder_name.split(" ")[-1] if prospect.founder_name else "Decision Maker",
                linkedin_url=prospect.founder_linkedin,
                source=LeadSourceEnum.AI_LEAD_MINER,
                custom_fields={
                    "linkedin": prospect.founder_linkedin,
                    "icp_score": prospect.icp_score,
                },
            )
            db.add(contact)
            await db.flush()

        # Create lead
        lead = Lead(
            tenant_id=tenant_id,
            contact_id=contact.id if contact else None,
            company_id=company.id,
            title=f"AI Miner: {prospect.company_name}",
            description=f"Discovered via AI Lead Miner (ICP Score: {prospect.icp_score})\n\n{prospect.icp_reason}\n\nRecommended Pitch: {prospect.recommended_pitch}",
            status="new",
            source=LeadSourceEnum.AI_LEAD_MINER,
            source_id=str(icp_id),
            ai_score=prospect.icp_score,
            ai_score_reason=prospect.icp_reason,
            ai_next_action=prospect.recommended_next_action,
            ai_next_action_confidence=prospect.confidence,
            ai_summary=prospect.recommended_pitch,
            custom_fields={
                "icp_id": str(icp_id),
                "prospect_data": prospect.raw_data,
                "recommended_pitch": prospect.recommended_pitch,
            },
        )
        db.add(lead)
        await db.flush()

        # Create touchpoint
        from app.models import Touchpoint
        touchpoint = Touchpoint(
            tenant_id=tenant_id,
            contact_id=contact.id if contact else None,
            lead_id=lead.id,
            source="ai_lead_miner",
            medium="prospecting",
            campaign=f"ICP: {prospect.company_name}",
            interaction_type="discovery",
            integration_id=None,
            external_id=str(icp_id),
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(touchpoint)

        # Create activity
        from app.models import Activity, ActivityTypeEnum
        activity = Activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=contact.id if contact else None,
            company_id=company.id,
            type=ActivityTypeEnum.LEAD_CREATED,
            subject=f"AI Lead Miner: {prospect.company_name}",
            description=f"Discovered via AI Lead Miner (Score: {prospect.icp_score})",
            metadata={"icp_score": prospect.icp_score, "icp_id": str(icp_id)},
            is_ai_generated=True,
        )
        db.add(activity)


# Need ICPProfile model - will add to models
from app.models import ICPProfile