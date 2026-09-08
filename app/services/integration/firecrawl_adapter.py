"""
Firecrawl Integration Adapter for Globexa CRM.
Searches for leads from the web using Firecrawl API.
"""
from abc import ABC
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID
import httpx
import structlog
import json

from app.services.integration.adapter import IntegrationAdapter, LeadData, SyncResult

logger = structlog.get_logger()


@dataclass
class FirecrawlSearchParams:
    """Parameters for Firecrawl lead search."""
    query: str
    limit: int = 10
    location: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    technologies: Optional[List[str]] = None


class FirecrawlAdapter(IntegrationAdapter):
    """Firecrawl web search adapter for lead generation."""
    
    @property
    def integration_type(self) -> str:
        return "firecrawl"
    
    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """Validate Firecrawl API key."""
        api_key = credentials.get("api_key")
        if not api_key:
            return False
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://api.firecrawl.dev/v0/health",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                return response.status_code == 200
        except Exception as e:
            logger.error("Firecrawl credential validation failed", error=type(e).__name__)
            return False
    
    async def sync_leads(
        self,
        integration_config: Dict[str, Any],
        credentials: Dict[str, Any],
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> SyncResult:
        """Search for leads using Firecrawl."""
        api_key = credentials.get("api_key")
        if not api_key:
            return SyncResult(success=False, error_message="Missing Firecrawl API key")
        
        search_params = integration_config.get("search_params", {})
        query = search_params.get("query", "")
        if not query:
            return SyncResult(success=False, error_message="Search query required in integration config")
        
        leads = []
        errors = []
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Firecrawl search endpoint
                payload = {
                    "query": query,
                    "limit": limit or search_params.get("limit", 10),
                    "scrapeOptions": {
                        "formats": ["markdown", "html"],
                        "onlyMainContent": True,
                    }
                }
                
                if search_params.get("location"):
                    payload["location"] = search_params["location"]
                
                response = await client.post(
                    "https://api.firecrawl.dev/v0/search",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                
                for result in data.get("data", []):
                    try:
                        lead_data = self._parse_firecrawl_result(result, query)
                        leads.append(lead_data)
                    except Exception as e:
                        errors.append({"url": result.get("url", "unknown"), "error": str(e)})
                        
        except httpx.HTTPStatusError as e:
            return SyncResult(
                success=False,
                error_message=f"Firecrawl API error: {e.response.text}",
                error_details={"status_code": e.response.status_code},
            )
        except Exception as e:
            logger.error("Firecrawl sync failed", error=type(e).__name__)
            return SyncResult(success=False, error_message=type(e).__name__)
        
        return SyncResult(
            success=True,
            records_processed=len(leads) + len(errors),
            records_created=len(leads),
            records_failed=len(errors),
            leads=leads,
        )
    
    def _parse_firecrawl_result(self, result: dict, search_query: str) -> LeadData:
        """Parse Firecrawl search result into standardized LeadData."""
        metadata = result.get("metadata", {})
        markdown = result.get("markdown", "")
        
        # Extract contact info from metadata and content
        url = result.get("url", "")
        title = metadata.get("title", "")
        description = metadata.get("description", "")
        
        # Try to extract email from content
        import re
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', markdown)
        email = emails[0] if emails else ""
        
        # Extract company name from title or URL
        company_name = title
        if not company_name and url:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.replace("www.", "")
            company_name = domain.split(".")[0].title()
        
        # Extract person name if available
        first_name = ""
        last_name = ""
        
        # Try to find person name in content
        name_patterns = [
            r"(?:CEO|CTO|CFO|COO|Founder|Co-Founder|Director|Manager|Head of|VP|Vice President)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s*(?:CEO|CTO|CFO|COO|Founder|Director|Manager)",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, markdown, re.IGNORECASE)
            if match:
                full_name = match.group(1).strip()
                name_parts = full_name.split()
                if len(name_parts) >= 2:
                    first_name = name_parts[0]
                    last_name = " ".join(name_parts[1:])
                break
        
        # Determine source from URL
        source = "web"
        if "linkedin.com" in url:
            source = "linkedin"
        elif "twitter.com" in url or "x.com" in url:
            source = "twitter"
        elif "github.com" in url:
            source = "github"
        elif "crunchbase.com" in url:
            source = "crunchbase"
        
        # Extract technologies if available
        tech_keywords = ["React", "Vue", "Angular", "Python", "Node.js", "Go", "Rust", "Java", "AWS", "GCP", "Azure", "Kubernetes", "Docker", "PostgreSQL", "MongoDB", "Redis"]
        found_techs = [tech for tech in tech_keywords if tech.lower() in markdown.lower()]
        
        return LeadData(
            email=email,
            first_name=first_name,
            last_name=last_name,
            title="",  # Could be extracted from content
            company_name=company_name,
            company_domain=url,
            source=source,
            medium="organic",
            utm_source="firecrawl",
            utm_medium="web_search",
            utm_campaign=search_query[:100],
            utm_content=url,
            source_id=url,
            raw_data=result,
            custom_fields={
                "firecrawl_url": url,
                "firecrawl_title": title,
                "firecrawl_description": description,
                "firecrawl_markdown": markdown[:5000],  # Truncate
                "technologies": found_techs,
                "search_query": search_query,
            },
        )
    
    async def get_webhook_events(self, payload: Dict[str, Any], secret: str) -> List[Dict[str, Any]]:
        """Firecrawl doesn't have webhooks - uses polling."""
        return []
    
    async def setup_webhook(self, credentials: Dict[str, Any], webhook_url: str, events: List[str]) -> Dict[str, Any]:
        """Firecrawl doesn't support webhooks."""
        return {"message": "Firecrawl uses polling, not webhooks"}
    
    async def remove_webhook(self, credentials: Dict[str, Any], webhook_id: str) -> bool:
        """Firecrawl doesn't support webhooks."""
        return True
    
    async def search_leads(
        self,
        credentials: Dict[str, Any],
        search_params: FirecrawlSearchParams,
    ) -> SyncResult:
        """Direct search method for on-demand lead searching."""
        api_key = credentials.get("api_key")
        if not api_key:
            return SyncResult(success=False, error_message="Missing Firecrawl API key")
        
        leads = []
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "query": search_params.query,
                    "limit": search_params.limit,
                    "scrapeOptions": {
                        "formats": ["markdown", "html"],
                        "onlyMainContent": True,
                    }
                }
                
                if search_params.location:
                    payload["location"] = search_params.location
                
                response = await client.post(
                    "https://api.firecrawl.dev/v0/search",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                
                for result in data.get("data", []):
                    try:
                        lead_data = self._parse_firecrawl_result(result, search_params.query)
                        leads.append(lead_data)
                    except Exception as e:
                        logger.error("Failed to parse Firecrawl result", error=type(e).__name__)
                        
        except httpx.HTTPStatusError as e:
            return SyncResult(
                success=False,
                error_message=f"Firecrawl API error: {e.response.text}",
                error_details={"status_code": e.response.status_code},
            )
        except Exception as e:
            logger.error("Firecrawl search failed", error=type(e).__name__)
            return SyncResult(success=False, error_message=type(e).__name__)
        
        return SyncResult(
            success=True,
            records_processed=len(leads),
            records_created=len(leads),
            leads=leads,
        )


# Register the adapter
def get_firecrawl_adapter() -> FirecrawlAdapter:
    """Factory function to get Firecrawl adapter instance."""
    return FirecrawlAdapter()