"""
Tasks, Notes, Activities API routes for Globexa CRM.
"""
from app.api.v1.tasks.router import tasks_router, notes_router, activities_router

__all__ = ["tasks_router", "notes_router", "activities_router"]
