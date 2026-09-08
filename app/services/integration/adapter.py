"""
Integration Framework for Globexa CRM.
Base adapter interface and provider-specific implementations.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, AsyncGenerator
from uuid import UUID
import httpx
import structlog
import json
import csv
import io
from email.parser import BytesParser
from email.policy import default

# Import FirecrawlAdapter to avoid circular imports
try:
    from app.services.integration.firecrawl_adapter import FirecrawlAdapter
except ImportError:
    FirecrawlAdapter = None

logger = structlog.get_logger()


@dataclass
class LeadData:
    """Standardized lead data from integrations."""
    # Required
    email: str
    # Optional
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    title: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    # Address
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    # Attribution
    source: Optional[str] = None
    medium: Optional[str] = None
    campaign: Optional[str] = None
    content: Optional[str] = None
    term: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    referrer_url: Optional[str] = None
    landing_page: Optional[str] = None
    # Source tracking
    source_id: Optional[str] = None  # External ID
    integration_id: Optional[str] = None
    # Custom fields
    custom_fields: Optional[Dict[str, Any]] = None
    # Raw data for debugging
    raw_data: Optional[Dict[str, Any]] = None


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    records_processed: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_failed: int = 0
    records_skipped: int = 0
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    leads: Optional[List[LeadData]] = None


class IntegrationAdapter(ABC):
    """Abstract base class for integration adapters."""

    @property
    @abstractmethod
    def integration_type(self) -> str:
        """Integration type identifier."""
        pass

    @abstractmethod
    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """Validate integration credentials."""
        pass

    @abstractmethod
    async def sync_leads(
        self,
        integration_config: Dict[str, Any],
        credentials: Dict[str, Any],
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> SyncResult:
        """Sync leads from the integration."""
        pass

    @abstractmethod
    async def get_webhook_events(self, payload: Dict[str, Any], secret: str) -> List[Dict[str, Any]]:
        """Parse webhook events into standardized format."""
        pass

    @abstractmethod
    async def setup_webhook(self, credentials: Dict[str, Any], webhook_url: str, events: List[str]) -> Dict[str, Any]:
        """Setup webhook on the provider."""
        pass

    @abstractmethod
    async def remove_webhook(self, credentials: Dict[str, Any], webhook_id: str) -> bool:
        """Remove webhook from the provider."""
        pass


class MetaAdapter(IntegrationAdapter):
    """Meta (Facebook/Instagram) Lead Ads adapter."""

    @property
    def integration_type(self) -> str:
        return "meta"

    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """Validate Meta access token."""
        access_token = credentials.get("access_token")
        if not access_token:
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://graph.facebook.com/v18.0/me",
                    params={"access_token": access_token, "fields": "id,name"},
                )
                return response.status_code == 200
        except Exception:
            return False

    async def sync_leads(
        self,
        integration_config: Dict[str, Any],
        credentials: Dict[str, Any],
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> SyncResult:
        """Sync leads from Meta Lead Ads."""
        access_token = credentials.get("access_token")
        ad_account_id = integration_config.get("ad_account_id")
        page_id = integration_config.get("page_id")
        form_ids = integration_config.get("form_ids", [])

        if not access_token:
            return SyncResult(success=False, error_message="Missing access token")

        leads = []
        errors = []

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Determine which forms to sync
                if not form_ids:
                    # Get all forms for the page
                    response = await client.get(
                        f"https://graph.facebook.com/v18.0/{page_id}/leadgen_forms",
                        params={"access_token": access_token, "fields": "id,name,status"},
                    )
                    response.raise_for_status()
                    forms = response.json().get("data", [])
                    form_ids = [f["id"] for f in forms if f.get("status") == "ACTIVE"]

                for form_id in form_ids:
                    # Get leads for this form
                    params = {
                        "access_token": access_token,
                        "fields": "id,created_time,field_data,ad_id,campaign_id,adset_id",
                        "limit": limit or 100,
                    }
                    if since:
                        params["filtering"] = json.dumps([{
                            "field": "created_time",
                            "operator": "GREATER_THAN",
                            "value": since.strftime("%Y-%m-%d"),
                        }])

                    response = await client.get(
                        f"https://graph.facebook.com/v18.0/{form_id}/leads",
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()

                    for lead in data.get("data", []):
                        try:
                            lead_data = self._parse_meta_lead(lead, form_id)
                            leads.append(lead_data)
                        except Exception as e:
                            errors.append({"lead_id": lead.get("id"), "error": str(e)})

        except httpx.HTTPStatusError as e:
            return SyncResult(
                success=False,
                error_message=f"Meta API error: {e.response.text}",
                error_details={"status_code": e.response.status_code},
            )
        except Exception as e:
            return SyncResult(success=False, error_message=type(e).__name__)

        return SyncResult(
            success=True,
            records_processed=len(leads) + len(errors),
            records_created=len(leads),
            records_failed=len(errors),
            leads=leads,
        )

    def _parse_meta_lead(self, lead: dict, form_id: str) -> LeadData:
        """Parse Meta lead data into standardized format."""
        field_data = {item["name"]: item["values"][0] if item["values"] else "" for item in lead.get("field_data", [])}

        # Map common fields
        email = field_data.get("email", "").lower()
        first_name = field_data.get("first_name", field_data.get("fn", ""))
        last_name = field_data.get("last_name", field_data.get("ln", ""))
        phone = field_data.get("phone_number", field_data.get("phone", ""))
        company = field_data.get("company_name", field_data.get("company", ""))
        title = field_data.get("job_title", field_data.get("title", ""))

        # UTM parameters
        utm_source = field_data.get("utm_source", "facebook")
        utm_medium = field_data.get("utm_medium", "cpc")
        utm_campaign = field_data.get("utm_campaign", lead.get("campaign_id"))
        utm_content = field_data.get("utm_content", lead.get("ad_id"))
        utm_term = field_data.get("utm_term", lead.get("adset_id"))

        return LeadData(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            title=title,
            company_name=company,
            source="facebook",
            medium="cpc",
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_content=utm_content,
            utm_term=utm_term,
            source_id=lead.get("id"),
            integration_id=form_id,
            raw_data=lead,
            custom_fields=field_data,
        )

    async def get_webhook_events(self, payload: Dict[str, Any], secret: str) -> List[Dict[str, Any]]:
        """Parse Meta webhook events."""
        # Verify signature (Meta uses X-Hub-Signature-256)
        events = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "leadgen":
                    value = change.get("value", {})
                    events.append({
                        "event_type": "lead.created",
                        "event_data": value,
                        "lead_id": value.get("leadgen_id"),
                        "form_id": value.get("form_id"),
                        "page_id": entry.get("id"),
                    })
        return events

    async def setup_webhook(self, credentials: Dict[str, Any], webhook_url: str, events: List[str]) -> Dict[str, Any]:
        """Setup Meta webhook subscription."""
        access_token = credentials.get("access_token")
        page_id = credentials.get("page_id")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://graph.facebook.com/v18.0/{page_id}/subscribed_apps",
                params={
                    "access_token": access_token,
                    "subscribed_fields": json.dumps(["leadgen"]),
                },
            )
            response.raise_for_status()
            return response.json()

    async def remove_webhook(self, credentials: Dict[str, Any], webhook_id: str) -> bool:
        """Remove Meta webhook subscription."""
        access_token = credentials.get("access_token")
        page_id = credentials.get("page_id")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"https://graph.facebook.com/v18.0/{page_id}/subscribed_apps",
                params={"access_token": access_token},
            )
            return response.status_code == 200


class GoogleAdsAdapter(IntegrationAdapter):
    """Google Ads Lead Form Extensions adapter."""

    @property
    def integration_type(self) -> str:
        return "google_ads"

    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """Validate Google Ads OAuth token."""
        access_token = credentials.get("access_token")
        if not access_token:
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                return response.status_code == 200
        except Exception:
            return False

    async def sync_leads(
        self,
        integration_config: Dict[str, Any],
        credentials: Dict[str, Any],
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> SyncResult:
        """Sync leads from Google Ads Lead Forms."""
        access_token = credentials.get("access_token")
        developer_token = credentials.get("developer_token")
        customer_id = integration_config.get("customer_id")

        if not all([access_token, developer_token, customer_id]):
            return SyncResult(success=False, error_message="Missing required credentials")

        leads = []

        try:
            # Google Ads API uses gRPC/REST hybrid
            # This is a simplified version using the REST API
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "developer-token": developer_token,
                }

                # Query for lead form submissions
                query_template = """
                    SELECT
                        lead_form_submission_data.lead_form_submission_fields,
                        lead_form_submission_data.submission_date_time,
                        lead_form_submission_data.gclid,
                        campaign.id,
                        campaign.name,
                        ad_group.id,
                        ad_group.name
                    FROM lead_form_submission_data
                    WHERE lead_form_submission_data.submission_date_time >= '{since}'
                    LIMIT {limit}
                """
                # GAQL accepts no bound parameters; only typed date and bounded int enter the template.
                query = query_template.format(
                    since=since.strftime("%Y-%m-%d") if since else "2020-01-01",
                    limit=max(1, min(int(limit or 1000), 1000)),
                )

                response = await client.post(
                    f"https://googleads.googleapis.com/v15/customers/{customer_id}/googleAds:search",
                    headers=headers,
                    json={"query": query},
                )
                response.raise_for_status()
                data = response.json()

                for row in data.get("results", []):
                    try:
                        lead_data = self._parse_google_ads_lead(row)
                        leads.append(lead_data)
                    except Exception as e:
                        logger.error("Failed to parse Google Ads lead", error=type(e).__name__)

        except Exception as e:
            return SyncResult(success=False, error_message=type(e).__name__)

        return SyncResult(
            success=True,
            records_processed=len(leads),
            records_created=len(leads),
            leads=leads,
        )

    def _parse_google_ads_lead(self, row: dict) -> LeadData:
        """Parse Google Ads lead data."""
        submission = row.get("leadFormSubmissionData", {})
        fields = submission.get("leadFormSubmissionFields", [])

        field_data = {}
        for field in fields:
            field_data[field.get("fieldName", "")] = field.get("stringValue", "")

        email = field_data.get("Email", "").lower()
        first_name = field_data.get("First Name", "")
        last_name = field_data.get("Last Name", "")
        phone = field_data.get("Phone", "")
        company = field_data.get("Company Name", "")
        title = field_data.get("Job Title", "")

        return LeadData(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            title=title,
            company_name=company,
            source="google",
            medium="cpc",
            utm_source="google",
            utm_medium="cpc",
            utm_campaign=row.get("campaign", {}).get("name"),
            utm_content=row.get("adGroup", {}).get("name"),
            source_id=submission.get("gclid"),
            raw_data=row,
            custom_fields=field_data,
        )

    async def get_webhook_events(self, payload: Dict[str, Any], secret: str) -> List[Dict[str, Any]]:
        """Google Ads doesn't have native webhooks for lead forms."""
        return []

    async def setup_webhook(self, credentials: Dict[str, Any], webhook_url: str, events: List[str]) -> Dict[str, Any]:
        return {"message": "Google Ads lead forms use polling, not webhooks"}

    async def remove_webhook(self, credentials: Dict[str, Any], webhook_id: str) -> bool:
        return True


class LinkedInAdapter(IntegrationAdapter):
    """LinkedIn Lead Gen Forms adapter."""

    @property
    def integration_type(self) -> str:
        return "linkedin"

    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        access_token = credentials.get("access_token")
        if not access_token:
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://api.linkedin.com/v2/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                return response.status_code == 200
        except Exception:
            return False

    async def sync_leads(
        self,
        integration_config: Dict[str, Any],
        credentials: Dict[str, Any],
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> SyncResult:
        """Sync leads from LinkedIn Lead Gen Forms."""
        access_token = credentials.get("access_token")
        account_urn = integration_config.get("account_urn")  # e.g., "urn:li:sponsoredAccount:123"
        form_ids = integration_config.get("form_ids", [])

        if not all([access_token, account_urn]):
            return SyncResult(success=False, error_message="Missing required credentials")

        leads = []

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "LinkedIn-Version": "202310",
                }

                if not form_ids:
                    # Get all forms for the account
                    response = await client.get(
                        f"https://api.linkedin.com/rest/leadGenForms",
                        headers=headers,
                        params={"q": "criteria", "accountUrn": account_urn},
                    )
                    response.raise_for_status()
                    forms = response.json().get("elements", [])
                    form_ids = [f["id"] for f in forms]

                for form_id in form_ids:
                    # Get leads for this form
                    params = {
                        "formUrn": form_id,
                        "q": "criteria",
                        "count": limit or 100,
                    }
                    if since:
                        params["startTime"] = int(since.timestamp() * 1000)

                    response = await client.get(
                        "https://api.linkedin.com/rest/leadGenFormResponses",
                        headers=headers,
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()

                    for lead in data.get("elements", []):
                        try:
                            lead_data = self._parse_linkedin_lead(lead, form_id)
                            leads.append(lead_data)
                        except Exception as e:
                            logger.error("Failed to parse LinkedIn lead", error=type(e).__name__)

        except Exception as e:
            return SyncResult(success=False, error_message=type(e).__name__)

        return SyncResult(
            success=True,
            records_processed=len(leads),
            records_created=len(leads),
            leads=leads,
        )

    def _parse_linkedin_lead(self, lead: dict, form_id: str) -> LeadData:
        """Parse LinkedIn lead data."""
        # LinkedIn returns field data as question/answer pairs
        field_data = {}
        for answer in lead.get("answers", []):
            question = answer.get("question", {})
            field_data[question.get("key", "")] = answer.get("answer", "")

        email = field_data.get("email", "").lower()
        first_name = field_data.get("firstName", "")
        last_name = field_data.get("lastName", "")
        phone = field_data.get("phoneNumber", "")
        company = field_data.get("companyName", "")
        title = field_data.get("jobTitle", "")

        return LeadData(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            title=title,
            company_name=company,
            source="linkedin",
            medium="cpc",
            utm_source="linkedin",
            utm_medium="cpc",
            source_id=lead.get("id"),
            integration_id=form_id,
            raw_data=lead,
            custom_fields=field_data,
        )

    async def get_webhook_events(self, payload: Dict[str, Any], secret: str) -> List[Dict[str, Any]]:
        """Parse LinkedIn webhook events."""
        events = []
        # LinkedIn webhook format
        for element in payload.get("elements", []):
            events.append({
                "event_type": "lead.created",
                "event_data": element,
                "lead_id": element.get("id"),
                "form_id": element.get("formUrn"),
            })
        return events

    async def setup_webhook(self, credentials: Dict[str, Any], webhook_url: str, events: List[str]) -> Dict[str, Any]:
        """Setup LinkedIn webhook."""
        access_token = credentials.get("access_token")
        account_urn = credentials.get("account_urn")

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "LinkedIn-Version": "202310",
            }
            response = await client.post(
                "https://api.linkedin.com/rest/webhookSubscriptions",
                headers=headers,
                json={
                    "accountUrn": account_urn,
                    "webhookUrl": webhook_url,
                    "events": ["LEAD_GEN_FORM_RESPONSE_CREATED"],
                },
            )
            response.raise_for_status()
            return response.json()

    async def remove_webhook(self, credentials: Dict[str, Any], webhook_id: str) -> bool:
        """Remove LinkedIn webhook."""
        access_token = credentials.get("access_token")
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {access_token}", "LinkedIn-Version": "202310"}
            response = await client.delete(
                f"https://api.linkedin.com/rest/webhookSubscriptions/{webhook_id}",
                headers=headers,
            )
            return response.status_code in [200, 204]


class ApolloAdapter(IntegrationAdapter):
    """Apollo.io adapter for lead enrichment and prospecting."""

    @property
    def integration_type(self) -> str:
        return "apollo"

    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        api_key = credentials.get("api_key")
        if not api_key:
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://api.apollo.io/v1/auth/health",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                return response.status_code == 200
        except Exception:
            return False

    async def sync_leads(
        self,
        integration_config: Dict[str, Any],
        credentials: Dict[str, Any],
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> SyncResult:
        """Sync leads from Apollo (search/export)."""
        api_key = credentials.get("api_key")
        if not api_key:
            return SyncResult(success=False, error_message="Missing API key")

        leads = []

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }

                # Search for contacts/accounts based on config
                search_params = integration_config.get("search_params", {})
                search_params.update({
                    "per_page": limit or 100,
                    "page": 1,
                })

                if since:
                    search_params["updated_at_after"] = since.isoformat()

                response = await client.post(
                    "https://api.apollo.io/v1/mixed_people/search",
                    headers=headers,
                    json=search_params,
                )
                response.raise_for_status()
                data = response.json()

                for person in data.get("people", []):
                    try:
                        lead_data = self._parse_apollo_person(person)
                        leads.append(lead_data)
                    except Exception as e:
                        logger.error("Failed to parse Apollo person", error=type(e).__name__)

        except Exception as e:
            return SyncResult(success=False, error_message=type(e).__name__)

        return SyncResult(
            success=True,
            records_processed=len(leads),
            records_created=len(leads),
            leads=leads,
        )

    def _parse_apollo_person(self, person: dict) -> LeadData:
        """Parse Apollo person data."""
        email = person.get("email", "").lower()
        first_name = person.get("first_name", "")
        last_name = person.get("last_name", "")
        phone = person.get("phone_numbers", [{}])[0].get("number", "") if person.get("phone_numbers") else ""
        title = person.get("title", "")
        
        company = person.get("organization", {})
        company_name = company.get("name", "")
        company_domain = company.get("domain", "")

        return LeadData(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            title=title,
            company_name=company_name,
            company_domain=company_domain,
            source="apollo",
            medium="prospecting",
            utm_source="apollo",
            utm_medium="prospecting",
            source_id=person.get("id"),
            raw_data=person,
            custom_fields={
                "linkedin_url": person.get("linkedin_url"),
                "twitter_url": person.get("twitter_url"),
                "city": person.get("city"),
                "state": person.get("state"),
                "country": person.get("country"),
            },
        )

    async def get_webhook_events(self, payload: Dict[str, Any], secret: str) -> List[Dict[str, Any]]:
        """Apollo webhooks for contact updates."""
        events = []
        for item in payload.get("data", []):
            events.append({
                "event_type": "contact.updated",
                "event_data": item,
                "contact_id": item.get("id"),
            })
        return events

    async def setup_webhook(self, credentials: Dict[str, Any], webhook_url: str, events: List[str]) -> Dict[str, Any]:
        """Setup Apollo webhook."""
        api_key = credentials.get("api_key")
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            response = await client.post(
                "https://api.apollo.io/v1/webhooks",
                headers=headers,
                json={"url": webhook_url, "events": events},
            )
            response.raise_for_status()
            return response.json()

    async def remove_webhook(self, credentials: Dict[str, Any], webhook_id: str) -> bool:
        api_key = credentials.get("api_key")
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = await client.delete(
                f"https://api.apollo.io/v1/webhooks/{webhook_id}",
                headers=headers,
            )
            return response.status_code in [200, 204]


class CSVAdapter(IntegrationAdapter):
    """CSV/Excel import adapter."""

    @property
    def integration_type(self) -> str:
        return "csv"

    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        # CSV doesn't need credentials, just file access
        return True

    async def sync_leads(
        self,
        integration_config: Dict[str, Any],
        credentials: Dict[str, Any],
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> SyncResult:
        """Parse CSV file and return leads."""
        file_content = integration_config.get("file_content")  # Base64 or raw
        file_path = integration_config.get("file_path")
        field_mapping = integration_config.get("field_mapping", {})

        if not file_content and not file_path:
            return SyncResult(success=False, error_message="No file provided")

        leads = []

        try:
            # Decode file content
            if file_content:
                import base64
                content = base64.b64decode(file_content).decode("utf-8")
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

            # Parse CSV
            reader = csv.DictReader(io.StringIO(content))
            
            for i, row in enumerate(reader):
                if limit and i >= limit:
                    break

                try:
                    lead_data = self._parse_csv_row(row, field_mapping)
                    leads.append(lead_data)
                except Exception as e:
                    logger.error("Failed to parse CSV row", row=i, error=type(e).__name__)

        except Exception as e:
            return SyncResult(success=False, error_message=type(e).__name__)

        return SyncResult(
            success=True,
            records_processed=len(leads),
            records_created=len(leads),
            leads=leads,
        )

    def _parse_csv_row(self, row: dict, field_mapping: dict) -> LeadData:
        """Parse CSV row with field mapping."""
        # Default mapping
        mapping = {
            "email": ["email", "e-mail", "email_address"],
            "first_name": ["first_name", "firstname", "fname", "given_name"],
            "last_name": ["last_name", "lastname", "lname", "surname"],
            "phone": ["phone", "phone_number", "telephone", "mobile"],
            "title": ["title", "job_title", "position"],
            "company_name": ["company", "company_name", "organization", "org"],
        }
        mapping.update(field_mapping)

        def get_value(keys):
            for key in keys:
                if key in row and row[key]:
                    return row[key]
            return None

        email = (get_value(mapping["email"]) or "").lower()
        first_name = get_value(mapping["first_name"]) or ""
        last_name = get_value(mapping["last_name"]) or ""
        phone = get_value(mapping["phone"]) or ""
        title = get_value(mapping["title"]) or ""
        company = get_value(mapping["company_name"]) or ""

        return LeadData(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            title=title,
            company_name=company,
            source="csv_import",
            medium="import",
            utm_source="csv",
            utm_medium="import",
            raw_data=row,
            custom_fields=row,
        )

    async def get_webhook_events(self, payload: Dict[str, Any], secret: str) -> List[Dict[str, Any]]:
        return []

    async def setup_webhook(self, credentials: Dict[str, Any], webhook_url: str, events: List[str]) -> Dict[str, Any]:
        return {"message": "CSV imports don't use webhooks"}

    async def remove_webhook(self, credentials: Dict[str, Any], webhook_id: str) -> bool:
        return True


class WebhookAdapter(IntegrationAdapter):
    """Generic webhook adapter for custom integrations."""

    @property
    def integration_type(self) -> str:
        return "webhook"

    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        return True

    async def sync_leads(
        self,
        integration_config: Dict[str, Any],
        credentials: Dict[str, Any],
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> SyncResult:
        # Webhook adapter doesn't poll - it receives pushes
        return SyncResult(success=True, message="Webhook adapter receives pushes, use get_webhook_events")

    async def get_webhook_events(self, payload: Dict[str, Any], secret: str) -> List[Dict[str, Any]]:
        """Parse generic webhook payload."""
        # Verify signature if secret provided
        if secret:
            import hmac
            import hashlib
            expected = payload.pop("signature", None)
            if expected:
                body = json.dumps(payload, separators=(",", ":")).encode()
                computed = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                if not hmac.compare_digest(computed, expected):
                    return [{"error": "Invalid signature"}]

        # Try to extract lead data from common formats
        events = []
        
        # Format 1: Direct lead object
        if "email" in payload:
            events.append({
                "event_type": "lead.created",
                "event_data": payload,
                "lead_data": self._extract_lead(payload),
            })
        # Format 2: Array of leads
        elif "leads" in payload and isinstance(payload["leads"], list):
            for lead in payload["leads"]:
                events.append({
                    "event_type": "lead.created",
                    "event_data": lead,
                    "lead_data": self._extract_lead(lead),
                })
        # Format 3: Nested data
        elif "data" in payload:
            events.append({
                "event_type": "lead.created",
                "event_data": payload["data"],
                "lead_data": self._extract_lead(payload["data"]),
            })

        return events

    def _extract_lead(self, data: dict) -> LeadData:
        """Extract lead data from webhook payload."""
        return LeadData(
            email=data.get("email", "").lower(),
            first_name=data.get("first_name", data.get("firstName", "")),
            last_name=data.get("last_name", data.get("lastName", "")),
            phone=data.get("phone", data.get("phoneNumber", "")),
            title=data.get("title", data.get("jobTitle", "")),
            company_name=data.get("company", data.get("companyName", "")),
            source=data.get("source", "webhook"),
            medium=data.get("medium", "webhook"),
            utm_source=data.get("utm_source"),
            utm_medium=data.get("utm_medium"),
            utm_campaign=data.get("utm_campaign"),
            utm_content=data.get("utm_content"),
            utm_term=data.get("utm_term"),
            source_id=data.get("id", data.get("lead_id")),
            raw_data=data,
            custom_fields=data,
        )

    async def setup_webhook(self, credentials: Dict[str, Any], webhook_url: str, events: List[str]) -> Dict[str, Any]:
        return {"message": "Webhook URL configured", "url": webhook_url}

    async def remove_webhook(self, credentials: Dict[str, Any], webhook_id: str) -> bool:
        return True


class EmailInboxAdapter(IntegrationAdapter):
    """Email inbox parser for lead capture."""

    @property
    def integration_type(self) -> str:
        return "email_inbox"

    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        # Would validate IMAP/SMTP credentials
        return True

    async def sync_leads(
        self,
        integration_config: Dict[str, Any],
        credentials: Dict[str, Any],
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> SyncResult:
        """Parse emails from inbox for leads."""
        # This would connect via IMAP and parse emails
        # Simplified implementation
        return SyncResult(success=True, message="Email inbox sync not fully implemented")

    async def get_webhook_events(self, payload: Dict[str, Any], secret: str) -> List[Dict[str, Any]]:
        """Parse inbound email webhook (e.g., from Resend, SendGrid, etc.)."""
        events = []
        
        # Handle Resend inbound email format
        if "from" in payload and "to" in payload:
            events.append({
                "event_type": "email.received",
                "event_data": payload,
                "lead_data": self._parse_email_lead(payload),
            })

        return events

    def _parse_email_lead(self, email_data: dict) -> LeadData:
        """Parse email into lead data."""
        from_addr = email_data.get("from", "")
        # Extract email from "Name <email@domain.com>"
        import re
        email_match = re.search(r"[\w\.-]+@[\w\.-]+", from_addr)
        email = email_match.group(0) if email_match else ""

        # Extract name
        name_match = re.search(r"^([^<]+)", from_addr)
        name = name_match.group(1).strip() if name_match else ""
        name_parts = name.split(" ", 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        subject = email_data.get("subject", "")
        html = email_data.get("html", "")
        text = email_data.get("text", "")

        return LeadData(
            email=email.lower(),
            first_name=first_name,
            last_name=last_name,
            source="email_inbox",
            medium="email",
            utm_source="email",
            utm_medium="inbound",
            raw_data=email_data,
            custom_fields={
                "subject": subject,
                "html_content": html,
                "text_content": text,
                "to": email_data.get("to"),
                "cc": email_data.get("cc"),
            },
        )

    async def setup_webhook(self, credentials: Dict[str, Any], webhook_url: str, events: List[str]) -> Dict[str, Any]:
        return {"message": "Configure email provider to forward to this webhook"}

    async def remove_webhook(self, credentials: Dict[str, Any], webhook_id: str) -> bool:
        return True


class IntegrationAdapterFactory:
    """Factory for creating integration adapters."""

    _adapters = {
        "meta": MetaAdapter,
        "google_ads": GoogleAdsAdapter,
        "linkedin": LinkedInAdapter,
        "apollo": ApolloAdapter,
        "csv": CSVAdapter,
        "webhook": WebhookAdapter,
        "email_inbox": EmailInboxAdapter,
    }

    @classmethod
    def _get_adapters(cls):
        """Get adapters dictionary, including Firecrawl if available."""
        adapters = cls._adapters.copy()
        if FirecrawlAdapter is not None:
            adapters["firecrawl"] = FirecrawlAdapter
        return adapters

    @classmethod
    def get_adapter(cls, integration_type: str) -> IntegrationAdapter:
        adapter_class = cls._get_adapters().get(integration_type)
        if not adapter_class:
            raise ValueError(f"No adapter for integration type: {integration_type}")
        return adapter_class()

    @classmethod
    def register_adapter(cls, integration_type: str, adapter_class: type):
        cls._adapters[integration_type] = adapter_class


class IntegrationService:
    """High-level integration service."""

    def __init__(self):
        self.factory = IntegrationAdapterFactory()

    async def validate_integration(
        self,
        integration_type: str,
        credentials: Dict[str, Any],
    ) -> bool:
        """Validate integration credentials."""
        adapter = self.factory.get_adapter(integration_type)
        return await adapter.validate_credentials(credentials)

    async def sync_integration(
        self,
        integration_type: str,
        integration_config: Dict[str, Any],
        credentials: Dict[str, Any],
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> SyncResult:
        """Sync leads from integration."""
        adapter = self.factory.get_adapter(integration_type)
        return await adapter.sync_leads(integration_config, credentials, since, limit)

    async def process_webhook(
        self,
        integration_type: str,
        payload: Dict[str, Any],
        secret: str,
    ) -> List[Dict[str, Any]]:
        """Process webhook events."""
        adapter = self.factory.get_adapter(integration_type)
        return await adapter.get_webhook_events(payload, secret)

    async def setup_webhook(
        self,
        integration_type: str,
        credentials: Dict[str, Any],
        webhook_url: str,
        events: List[str],
    ) -> Dict[str, Any]:
        """Setup webhook on provider."""
        adapter = self.factory.get_adapter(integration_type)
        return await adapter.setup_webhook(credentials, webhook_url, events)

    async def remove_webhook(
        self,
        integration_type: str,
        credentials: Dict[str, Any],
        webhook_id: str,
    ) -> bool:
        """Remove webhook from provider."""
        adapter = self.factory.get_adapter(integration_type)
        return await adapter.remove_webhook(credentials, webhook_id)