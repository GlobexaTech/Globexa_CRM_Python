"""Compatibility interface backed by the authoritative computed PostgreSQL FTS indexes."""

from typing import Any, Dict, List, Optional, Protocol
from uuid import UUID
from sqlalchemy import func, literal_column, select
from app.core.search import PostgresSearch


class SearchBackend(Protocol):
    async def search(self, entity_type, query, tenant_id, filters=None, limit=20, offset=0): ...
    async def index(self, entity_type, entity_id, data, tenant_id): ...
    async def remove(self, entity_type, entity_id, tenant_id): ...


class PostgresFTSBackend:
    # Identifiers are application-owned model attributes, never caller SQL.
    entities = {
        "lead": "leads",
        "contact": "contacts",
        "deal": "deals",
        "company": "companies",
        "campaign": "campaigns",
        "task": "tasks",
        "note": "notes",
    }

    def __init__(self, db):
        self.db = db

    async def index(self, entity_type, entity_id, data, tenant_id):
        # Expression indexes update automatically in the entity write transaction.
        if entity_type not in self.entities:
            raise ValueError("Unsupported search entity")
        model, _ = PostgresSearch.entities[self.entities[entity_type]]
        if not await self.db.scalar(
            select(model.id).where(model.id == entity_id, model.tenant_id == tenant_id)
        ):
            raise ValueError("Search entity not found")
        await self.db.flush()

    async def remove(self, entity_type, entity_id, tenant_id):
        raise NotImplementedError(
            "Computed search indexes follow CRM entity deletion; independent removal is unsupported"
        )

    async def search(self, entity_type, query, tenant_id, filters=None, limit=20, offset=0):
        if (
            entity_type not in self.entities
            or not 1 <= limit <= 100
            or not 0 <= offset <= 100000
            or len(query) > 500
        ):
            raise ValueError("Invalid search")
        model, expression = PostgresSearch.entities[self.entities[entity_type]]
        vector = func.to_tsvector(literal_column("'simple'"), literal_column(expression))
        term = func.websearch_to_tsquery(literal_column("'simple'"), query)
        rank = func.ts_rank(vector, term)
        statement = select(
            model.id, rank.label("rank"), literal_column(expression).label("content")
        ).where(model.tenant_id == tenant_id, vector.op("@@")(term))
        for key, value in (filters or {}).items():
            if key not in model.__table__.columns or key in {"tenant_id", "id"}:
                raise ValueError("Unsupported search filter")
            statement = statement.where(getattr(model, key) == value)
        result = await self.db.execute(
            statement.order_by(rank.desc(), model.id).limit(limit).offset(offset)
        )
        return [dict(row) for row in result.mappings()]


class SearchService:
    """Unified search interface."""

    def __init__(self, backend: SearchBackend):
        self.backend = backend

    async def search_leads(
        self,
        tenant_id: UUID,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self.backend.search("lead", query, tenant_id, filters, limit, offset)

    async def search_contacts(
        self,
        tenant_id: UUID,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self.backend.search("contact", query, tenant_id, filters, limit, offset)

    async def search_deals(
        self,
        tenant_id: UUID,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self.backend.search("deal", query, tenant_id, filters, limit, offset)

    async def search_companies(
        self,
        tenant_id: UUID,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self.backend.search("company", query, tenant_id, filters, limit, offset)

    async def search_campaigns(
        self,
        tenant_id: UUID,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self.backend.search("campaign", query, tenant_id, filters, limit, offset)

    async def search_tasks(
        self,
        tenant_id: UUID,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self.backend.search("task", query, tenant_id, filters, limit, offset)

    async def search_notes(
        self,
        tenant_id: UUID,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self.backend.search("note", query, tenant_id, filters, limit, offset)

    async def index_entity(
        self,
        entity_type: str,
        entity_id: UUID,
        data: Dict[str, Any],
        tenant_id: UUID,
    ):
        await self.backend.index(entity_type, entity_id, data, tenant_id)

    async def remove_entity(
        self,
        entity_type: str,
        entity_id: UUID,
        tenant_id: UUID,
    ):
        await self.backend.remove(entity_type, entity_id, tenant_id)
