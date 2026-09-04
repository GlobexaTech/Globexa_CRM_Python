"""Integration service for managing integrations and credentials."""
from typing import Optional, Dict, Any, List
from uuid import UUID
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.encryption import (
    encrypt_credentials, decrypt_credentials,
    encrypt_api_key, decrypt_api_key,
    encrypt_oauth_tokens, decrypt_oauth_tokens,
    encrypt_webhook_secret, decrypt_webhook_secret,
)
from app.models import Integration, IntegrationCredential, WebhookEndpoint

logger = structlog.get_logger()


class IntegrationService:
    """Service for managing integrations with encrypted credentials."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_integration(
        self,
        tenant_id: UUID,
        type: str,
        name: str,
        config: Dict[str, Any],
        credentials: Dict[str, Any],
    ) -> Integration:
        """Create a new integration with encrypted credentials."""
        # Create integration record
        integration = Integration(
            tenant_id=tenant_id,
            type=type,
            name=name,
            config=config,
            status="active",
        )
        self.session.add(integration)
        await self.session.flush()
        
        # Encrypt and store credentials
        if credentials:
            await self._store_credentials(integration.id, credentials)
        
        await self.session.commit()
        await self.session.refresh(integration)
        return integration
    
    async def update_integration(
        self,
        integration_id: UUID,
        tenant_id: UUID,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        credentials: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
    ) -> Optional[Integration]:
        """Update an integration."""
        result = await self.session.execute(
            select(Integration).where(
                and_(Integration.id == integration_id, Integration.tenant_id == tenant_id)
            )
        )
        integration = result.scalar_one_or_none()
        
        if not integration:
            return None
        
        if name is not None:
            integration.name = name
        if config is not None:
            integration.config = config
        if status is not None:
            integration.status = status
        
        if credentials is not None:
            await self._update_credentials(integration_id, credentials)
        
        await self.session.commit()
        await self.session.refresh(integration)
        return integration
    
    async def get_integration(self, integration_id: UUID, tenant_id: UUID) -> Optional[Integration]:
        """Get integration by ID."""
        result = await self.session.execute(
            select(Integration).where(
                and_(Integration.id == integration_id, Integration.tenant_id == tenant_id)
            )
        )
        return result.scalar_one_or_none()
    
    async def list_integrations(self, tenant_id: UUID, type: Optional[str] = None) -> List[Integration]:
        """List integrations for a tenant."""
        query = select(Integration).where(Integration.tenant_id == tenant_id)
        if type:
            query = query.where(Integration.type == type)
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def delete_integration(self, integration_id: UUID, tenant_id: UUID) -> bool:
        """Delete an integration and its credentials."""
        result = await self.session.execute(
            select(Integration).where(
                and_(Integration.id == integration_id, Integration.tenant_id == tenant_id)
            )
        )
        integration = result.scalar_one_or_none()
        
        if not integration:
            return False
        
        # Credentials cascade delete via FK
        await self.session.delete(integration)
        await self.session.commit()
        return True
    
    async def get_decrypted_credentials(
        self, integration_id: UUID, tenant_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Get decrypted credentials for an integration."""
        # Verify integration belongs to tenant
        integration = await self.get_integration(integration_id, tenant_id)
        if not integration:
            return None
        
        # Get all credentials for this integration
        result = await self.session.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.integration_id == integration_id
            )
        )
        credentials = result.scalars().all()
        
        if not credentials:
            return {}
        
        # Decrypt all credentials
        decrypted = {}
        for cred in credentials:
            if cred.credentials_encrypted:
                try:
                    decrypted[cred.name] = decrypt_credentials(cred.credentials_encrypted)
                except Exception as e:
                    logger.error("Failed to decrypt credential", 
                                integration_id=str(integration_id), 
                                name=cred.name,
                                error=str(e))
                    decrypted[cred.name] = {}
        
        return decrypted
    
    async def get_decrypted_credential(
        self, integration_id: UUID, tenant_id: UUID, name: str
    ) -> Optional[str]:
        """Get a specific decrypted credential by name."""
        integration = await self.get_integration(integration_id, tenant_id)
        if not integration:
            return None
        
        result = await self.session.execute(
            select(IntegrationCredential).where(
                and_(
                    IntegrationCredential.integration_id == integration_id,
                    IntegrationCredential.name == name,
                )
            )
        )
        credential = result.scalar_one_or_none()
        
        if not credential or not credential.credentials_encrypted:
            return None
        
        try:
            data = decrypt_credentials(credential.credentials_encrypted)
            return data.get(name) if isinstance(data, dict) else data
        except Exception as e:
            logger.error("Failed to decrypt credential", 
                        integration_id=str(integration_id), 
                        name=name,
                        error=str(e))
            return None
    
    async def _store_credentials(self, integration_id: UUID, credentials: Dict[str, Any]) -> None:
        """Store encrypted credentials for an integration."""
        for name, value in credentials.items():
            if isinstance(value, dict):
                encrypted = encrypt_credentials(value)
            else:
                encrypted = encrypt_credentials({name: value})
            
            cred = IntegrationCredential(
                integration_id=integration_id,
                name=name,
                credentials_encrypted=encrypted,
            )
            self.session.add(cred)
    
    async def _update_credentials(self, integration_id: UUID, credentials: Dict[str, Any]) -> None:
        """Update credentials - delete old, insert new."""
        # Delete existing
        await self.session.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.integration_id == integration_id
            ).delete()
        )
        # Store new
        await self._store_credentials(integration_id, credentials)
    
    async def create_webhook_endpoint(
        self,
        tenant_id: UUID,
        integration_id: UUID,
        name: str,
        url_path: str,
        secret: str,
        events: List[str],
    ) -> WebhookEndpoint:
        """Create a webhook endpoint with encrypted secret."""
        encrypted_secret = encrypt_webhook_secret(secret)
        
        webhook = WebhookEndpoint(
            tenant_id=tenant_id,
            integration_id=integration_id,
            name=name,
            url_path=url_path,
            secret=encrypted_secret,
            events=events,
        )
        self.session.add(webhook)
        await self.session.commit()
        await self.session.refresh(webhook)
        return webhook
    
    async def get_webhook_secret(self, webhook_id: UUID, tenant_id: UUID) -> Optional[str]:
        """Get decrypted webhook secret."""
        result = await self.session.execute(
            select(WebhookEndpoint).where(
                and_(WebhookEndpoint.id == webhook_id, WebhookEndpoint.tenant_id == tenant_id)
            )
        )
        webhook = result.scalar_one_or_none()
        
        if not webhook:
            return None
        
        try:
            return decrypt_webhook_secret(webhook.secret)
        except Exception as e:
            logger.error("Failed to decrypt webhook secret", 
                        webhook_id=str(webhook_id), 
                        error=str(e))
            return None