"""PostgreSQL FTS search layer with Meilisearch-ready architecture."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func


class SearchBackend(ABC):
    """Abstract search backend interface."""
    
    @abstractmethod
    async def index(self, entity_type: str, entity_id: UUID, data: Dict[str, Any], tenant_id: UUID):
        """Index or update an entity."""
        pass
    
    @abstractmethod
    async def remove(self, entity_type: str, entity_id: UUID, tenant_id: UUID):
        """Remove an entity from index."""
        pass
    
    @abstractmethod
    async def search(
        self,
        entity_type: str,
        query: str,
        tenant_id: UUID,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search entities."""
        pass


class PostgresFTSBackend(SearchBackend):
    """PostgreSQL full-text search implementation using tsvector."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def index(self, entity_type: str, entity_id: UUID, data: Dict[str, Any], tenant_id: UUID):
        """Update tsvector column on entity."""
        # Map entity types to tables
        table_map = {
            "lead": "leads",
            "contact": "contacts",
            "deal": "deals",
            "company": "companies",
            "campaign": "campaigns",
            "task": "tasks",
            "note": "notes",
        }
        
        table = table_map.get(entity_type)
        if not table:
            return
        
        # Build searchable text from relevant fields
        searchable_fields = self._get_searchable_fields(entity_type, data)
        searchable_text = " ".join(searchable_fields)
        
        # Update tsvector column
        await self.db.execute(
            text(f"""
                UPDATE {table}
                SET search_vector = to_tsvector('english', :text)
                WHERE id = :id AND tenant_id = :tenant_id
            """),
            {"text": searchable_text, "id": str(entity_id), "tenant_id": str(tenant_id)}
        )
        await self.db.commit()
    
    async def remove(self, entity_type: str, entity_id: UUID, tenant_id: UUID):
        """Clear search vector (soft delete from search)."""
        table_map = {
            "lead": "leads",
            "contact": "contacts",
            "deal": "deals",
            "company": "companies",
            "campaign": "campaigns",
            "task": "tasks",
            "note": "notes",
        }
        
        table = table_map.get(entity_type)
        if not table:
            return
        
        await self.db.execute(
            text(f"""
                UPDATE {table}
                SET search_vector = NULL
                WHERE id = :id AND tenant_id = :tenant_id
            """),
            {"id": str(entity_id), "tenant_id": str(tenant_id)}
        )
        await self.db.commit()
    
    async def search(
        self,
        entity_type: str,
        query: str,
        tenant_id: UUID,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search using PostgreSQL FTS."""
        table_map = {
            "lead": ("leads", ["id", "title", "status", "source", "ai_score", "created_at"]),
            "contact": ("contacts", ["id", "first_name", "last_name", "email", "phone", "company_id", "created_at"]),
            "deal": ("deals", ["id", "title", "value", "stage_id", "pipeline_id", "expected_close_date", "created_at"]),
            "company": ("companies", ["id", "name", "domain", "industry", "size", "created_at"]),
            "campaign": ("campaigns", ["id", "name", "type", "status", "created_at"]),
            "task": ("tasks", ["id", "title", "status", "priority", "due_date", "created_at"]),
            "note": ("notes", ["id", "content", "lead_id", "deal_id", "created_at"]),
        }
        
        table_info = table_map.get(entity_type)
        if not table_info:
            return []
        
        table, fields = table_info
        
        # Build query with FTS
        # Use plainto_tsquery for simple queries, to_tsquery for advanced
        fts_query = func.plainto_tsquery('english', query)
        
        # Build field list for SELECT
        field_list = ", ".join(fields)
        
        # Build WHERE clause
        where_clauses = ["tenant_id = :tenant_id", "search_vector @@ :fts_query"]
        params = {"tenant_id": str(tenant_id), "fts_query": fts_query}
        
        if filters:
            for key, value in filters.items():
                if key in fields:
                    where_clauses.append(f"{key} = :{key}")
                    params[key] = value
        
        where_sql = " AND ".join(where_clauses)
        
        # Execute search with ranking
        sql = f"""
            SELECT {field_list}, ts_rank_cd(search_vector, :fts_query) as rank
            FROM {table}
            WHERE {where_sql}
            ORDER BY rank DESC, created_at DESC
            LIMIT :limit OFFSET :offset
        """
        
        params["limit"] = limit
        params["offset"] = offset
        
        result = await self.db.execute(text(sql), params)
        rows = result.mappings().all()
        
        return [dict(row) for row in rows]
    
    def _get_searchable_fields(self, entity_type: str, data: Dict[str, Any]) -> List[str]:
        """Extract searchable text fields for entity type."""
        fields = []
        
        if entity_type == "lead":
            fields.extend([
                data.get("title", ""),
                data.get("description", ""),
                data.get("source", "") if data.get("source") else "",
            ])
        elif entity_type == "contact":
            fields.extend([
                data.get("first_name", ""),
                data.get("last_name", ""),
                data.get("email", ""),
                data.get("phone", ""),
                data.get("title", ""),
                data.get("department", ""),
            ])
        elif entity_type == "deal":
            fields.extend([
                data.get("title", ""),
                data.get("description", ""),
            ])
        elif entity_type == "company":
            fields.extend([
                data.get("name", ""),
                data.get("domain", ""),
                data.get("industry", ""),
                data.get("description", ""),
            ])
        elif entity_type == "campaign":
            fields.extend([
                data.get("name", ""),
                data.get("description", ""),
            ])
        elif entity_type == "task":
            fields.extend([
                data.get("title", ""),
                data.get("description", ""),
            ])
        elif entity_type == "note":
            fields.append(data.get("content", ""))
        
        return [f for f in fields if f]


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