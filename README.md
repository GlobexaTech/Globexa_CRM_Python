# Globexa CRM

Multi-tenant AI-powered Sales CRM built with FastAPI, SQLAlchemy, and Celery.

## Features

- **Multi-tenancy**: Secure tenant isolation with row-level security
- **Authentication**: JWT + Google OAuth with role-based access control
- **Package-based entitlements**: Flexible feature flags and limits (not hard-coded)
- **AI Router**: Local (Ollama) + Cloud (NVIDIA NIM, OpenAI, Anthropic) with usage ledger
- **Background Workers**: Celery + Redis for campaigns, AI jobs, integrations
- **Email Provider Abstraction**: Resend, Gmail, Microsoft Graph, SMTP

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env
# Edit .env with your values

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload

# Start Celery worker (in another terminal)
celery -A app.workers.celery_app worker --loglevel=info

# Start Celery beat (in another terminal)
celery -A app.workers.celery_app beat --loglevel=info
```

## Project Structure

```
globexa_crm/
├── app/
│   ├── api/v1/           # API routes (auth, tenants, users, health)
│   ├── core/             # Config, database, security
│   ├── middleware/       # Tenant middleware
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic (auth, AI, email, etc.)
│   ├── workers/          # Celery tasks
│   └── main.py           # FastAPI app
├── alembic/              # Database migrations
├── tests/                # Tests
├── config.yaml           # Configuration
├── pyproject.toml        # Dependencies
└── .env.example          # Environment template
```

## API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc