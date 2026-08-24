"""
AI Proposal Generator Service for Globexa CRM.
Generates professional proposals from deal context and approved data.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import structlog
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Deal, Company, Contact, User, Proposal, ProposalTemplate, Product
from app.services.ai.router import get_ai_router, AITaskTypeEnum

logger = structlog.get_logger()


@dataclass
class ProposalData:
    """Structured proposal data from deal context."""
    deal: Deal
    company: Optional[Company]
    contact: Optional[Contact]
    products: List[Product]
    pricing: Dict[str, Any]
    terms: Dict[str, Any]
    meeting_notes: Optional[str]


@dataclass
class GeneratedProposal:
    """Generated proposal content."""
    title: str
    executive_summary: str
    solution_overview: str
    pricing_details: Dict[str, Any]
    terms: str
    next_steps: str
    cover_letter: Optional[str]


class ProposalGeneratorService:
    """AI-powered proposal generation from structured data."""

    def __init__(self):
        self.router = get_ai_router()

    async def generate_proposal(
        self,
        db: AsyncSession,
        deal_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        template_id: Optional[UUID] = None,
        customizations: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Proposal:
        """Generate a proposal for a deal."""
        # Load deal with all context
        result = await db.execute(
            select(Deal)
            .where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
            .options(
                selectinload(Deal.company),
                selectinload(Deal.contact).selectinload(Contact.company),
                selectinload(Deal.owner),
                selectinload(Deal.stage),
                selectinload(Deal.pipeline),
            )
        )
        deal = result.scalar_one_or_none()
        if not deal:
            raise ValueError(f"Deal {deal_id} not found")

        # Get products/pricing for deal
        products_result = await db.execute(
            select(Product).where(Product.tenant_id == tenant_id, Product.is_active == True)
        )
        products = products_result.scalars().all()

        # Get template if specified
        template = None
        if template_id:
            template_result = await db.execute(
                select(ProposalTemplate).where(
                    ProposalTemplate.id == template_id,
                    ProposalTemplate.tenant_id == tenant_id,
                )
            )
            template = template_result.scalar_one_or_none()

        # Build proposal data
        proposal_data = ProposalData(
            deal=deal,
            company=deal.company,
            contact=deal.contact,
            products=products,
            pricing=deal.custom_fields.get("pricing", {}) if deal.custom_fields else {},
            terms=deal.custom_fields.get("terms", {}) if deal.custom_fields else {},
            meeting_notes=deal.custom_fields.get("meeting_notes") if deal.custom_fields else None,
        )

        # Get AI generation
        generated = await self._generate_with_ai(
            db, proposal_data, template, customizations, tenant_id, user_id, correlation_id
        )

        # Create proposal record
        proposal = Proposal(
            tenant_id=tenant_id,
            deal_id=deal_id,
            title=generated.title,
            version=1,
            status="draft",
            executive_summary=generated.executive_summary,
            solution_overview=generated.solution_overview,
            pricing_details=generated.pricing_details,
            terms=generated.terms,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_ai_generated=True,
            ai_provider="nvidia",
            ai_model="nemotron-3-ultra",
            created_by_id=user_id,
        )
        db.add(proposal)
        await db.flush()

        # Create activity
        from app.models import Activity, ActivityTypeEnum
        activity = Activity(
            tenant_id=tenant_id,
            deal_id=deal_id,
            type=ActivityTypeEnum.AI_ACTION,
            subject=f"Proposal generated: {generated.title}",
            description=f"AI-generated proposal for {deal.company.name if deal.company else 'deal'}",
            user_id=user_id,
            metadata={
                "proposal_id": str(proposal.id),
                "template_id": str(template_id) if template_id else None,
            },
            is_ai_generated=True,
        )
        db.add(activity)

        await db.commit()
        await db.refresh(proposal)

        return proposal

    async def _generate_with_ai(
        self,
        db: AsyncSession,
        data: ProposalData,
        template: Optional[ProposalTemplate],
        customizations: Optional[Dict[str, Any]],
        tenant_id: UUID,
        user_id: UUID,
        correlation_id: Optional[str],
    ) -> GeneratedProposal:
        """Generate proposal content using AI."""
        
        # Build context
        context = {
            "deal": {
                "title": data.deal.title,
                "value": data.deal.value,
                "currency": data.deal.currency,
                "probability": data.deal.probability,
                "expected_close": data.deal.expected_close_date.isoformat() if data.deal.expected_close_date else None,
                "stage": data.deal.stage.name if data.deal.stage else None,
            },
            "company": {
                "name": data.company.name if data.company else None,
                "industry": data.company.industry if data.company else None,
                "size": data.company.size if data.company else None,
                "website": data.company.website if data.company else None,
            } if data.company else None,
            "contact": {
                "name": data.contact.full_name if data.contact else None,
                "title": data.contact.title if data.contact else None,
                "email": data.contact.email if data.contact else None,
            } if data.contact else None,
            "products": [
                {
                    "name": p.name,
                    "description": p.description,
                    "price": p.price,
                    "billing_cycle": p.billing_cycle,
                }
                for p in data.products
            ],
            "pricing": data.pricing,
            "terms": data.terms,
            "meeting_notes": data.meeting_notes,
            "template": {
                "name": template.name if template else None,
                "structure": template.structure if template else None,
            } if template else None,
            "customizations": customizations or {},
        }

        template_instruction = ""
        if template and template.structure:
            template_instruction = f"\n\nUse this template structure:\n{json.dumps(template.structure, indent=2)}"

        prompt = f"""
        Generate a professional sales proposal for this deal.
        
        Context:
        {json.dumps(context, indent=2, default=str)}
        
        {template_instruction}
        
        Customizations: {json.dumps(customizations or {}, indent=2)}
        
        Requirements:
        - Professional, persuasive tone
        - Executive summary highlighting value proposition
        - Solution overview tailored to company's industry/size
        - Clear pricing with optional packages
        - Standard terms & conditions
        - Clear next steps with timeline
        - Use company/contact names for personalization
        
        Return JSON:
        {{
            "title": "Proposal for [Company] - [Deal Title]",
            "executive_summary": "Compelling 2-3 paragraph summary...",
            "solution_overview": "Detailed solution description...",
            "pricing_details": {{
                "items": [
                    {{"name": "...", "description": "...", "quantity": 1, "unit_price": 10000, "total": 10000}}
                ],
                "subtotal": 10000,
                "discount": 0,
                "total": 10000,
                "currency": "USD"
            }},
            "terms": "Standard terms...",
            "next_steps": "1. Review & sign\n2. Onboarding kickoff\n3. Implementation",
            "cover_letter": "Optional personalized cover letter..."
        }}
        """

        result = await self.router.complete(
            task_type=AITaskTypeEnum.PROPOSAL_GENERATION,
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
                parsed = json.loads(result.content)
                return GeneratedProposal(**parsed)
            except (json.JSONDecodeError, TypeError):
                pass

        # Fallback
        return GeneratedProposal(
            title=f"Proposal for {data.company.name if data.company else data.deal.title}",
            executive_summary=f"We're excited to propose a solution for {data.company.name if data.company else 'your company'}.",
            solution_overview="Our solution addresses your key challenges...",
            pricing_details={"items": [], "subtotal": 0, "total": 0, "currency": "USD"},
            terms="Standard terms and conditions apply.",
            next_steps="1. Review proposal\n2. Schedule follow-up\n3. Sign agreement",
            cover_letter=None,
        )

    async def regenerate_section(
        self,
        db: AsyncSession,
        proposal_id: UUID,
        section: str,  # executive_summary, solution_overview, pricing, terms
        instructions: str,
        tenant_id: UUID,
        user_id: UUID,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Regenerate a specific section of a proposal."""
        result = await db.execute(
            select(Proposal).where(Proposal.id == proposal_id, Proposal.tenant_id == tenant_id)
        )
        proposal = result.scalar_one_or_none()
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        # Get deal context
        deal_result = await db.execute(
            select(Deal)
            .where(Deal.id == proposal.deal_id)
            .options(selectinload(Deal.company), selectinload(Deal.contact))
        )
        deal = deal_result.scalar_one_or_none()

        prompt = f"""
        Regenerate the '{section}' section of this proposal.
        
        Current proposal:
        Title: {proposal.title}
        Executive Summary: {proposal.executive_summary[:500]}
        Solution Overview: {proposal.solution_overview[:500]}
        Pricing: {json.dumps(proposal.pricing_details)}
        Terms: {proposal.terms[:500]}
        
        Deal: {deal.title if deal else 'N/A'}
        Company: {deal.company.name if deal and deal.company else 'N/A'}
        
        Instructions: {instructions}
        
        Return JSON with the updated section:
        {{
            "{section}": "Updated content..."
        }}
        """

        result = await self.router.complete(
            task_type=AITaskTypeEnum.PROPOSAL_GENERATION,
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
                return json.loads(result.content)
            except json.JSONDecodeError:
                pass

        return {section: "Regeneration failed - please try again"}


# Need imports
from sqlalchemy.orm import selectinload
from app.models import Product, ProposalTemplate
from datetime import timedelta