"""Tenant-aware search interface; PostgreSQL FTS is the first backend."""
from typing import Protocol
from sqlalchemy import func, literal_column, select
from app.models import Lead, Contact, Message, Task, Campaign, AgentDefinition, Company, Deal, Note, Conversation


class SearchBackend(Protocol):
    async def search(self, tenant_id, entity: str, query: str, limit: int = 20): ...


class PostgresSearch:
    entities = {
        "leads": (Lead, "coalesce(title,'')"),
        "contacts": (Contact, "coalesce(first_name,'') || ' ' || coalesce(last_name,'') || ' ' || coalesce(email,'')"),
        "messages": (Message, "body"), "tasks": (Task, "title"),
        "campaigns": (Campaign, "name"), "agents": (AgentDefinition, "name"),
        "companies": (Company, "name"), "deals": (Deal, "title"),
        "notes": (Note, "content"), "conversations": (Conversation, "subject"),
    }

    def __init__(self, db):
        self.db = db

    async def search(self, tenant_id, entity, query, limit=20):
        if entity not in self.entities or not 1 <= limit <= 100 or len(query) > 500:
            raise ValueError("Invalid search")
        model, expression = self.entities[entity]
        vector = func.to_tsvector(literal_column("'simple'"), literal_column(expression))
        term = func.websearch_to_tsquery(literal_column("'simple'"), query)
        rank = func.ts_rank(vector, term)
        relations = [field for field in ("conversation_id", "contact_id", "company_id", "lead_id", "deal_id") if hasattr(model, field)]
        result = await self.db.execute(select(model.id, rank.label("rank"), literal_column(expression).label("content"), *[getattr(model, field) for field in relations]).where(
            model.tenant_id == tenant_id, vector.op("@@")(term)).order_by(rank.desc(), model.id).limit(limit))
        return [{"id": str(row.id), "rank": row.rank, "entity": entity, "title": row.content[:120],
                 "snippet": row.content[:300], **{field: str(getattr(row, field)) if getattr(row, field) else None for field in relations}} for row in result]
