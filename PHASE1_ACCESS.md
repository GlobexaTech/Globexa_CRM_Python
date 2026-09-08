# Phase 1 Complete - Access Instructions

## Project Location
```
C:\Users\Globe\globexa_crm\
```

## What's Built (Phase 1 + 2 Foundation)

### Core Infrastructure
- **FastAPI Application** with structured logging, CORS, exception handling
- **SQLAlchemy 2.0 Async** models with PostgreSQL + asyncpg
- **Alembic Migrations** (2 migrations: initial schema + CRM models)
- **Multi-tenant Architecture** with row-level isolation
- **JWT Authentication** with access/refresh tokens, Google OAuth
- **RBAC System** with 6 roles (Owner→Viewer) and permission hierarchy
- **Package/Entitlement System** (STARTER/GROWTH/AI_PRO/ENTERPRISE)
- **Celery + Redis** background workers with 5 queues + beat scheduler
- **AI Router** with Ollama (local) + NVIDIA NIM (cloud) providers
- **Docker Compose** for full stack deployment

### Data Models (Phase 1)
- `tenants` - Top-level tenant isolation
- `users` - Global user accounts
- `memberships` - User-tenant-role relationships
- `subscriptions` - Billing/subscription tracking
- `feature_entitlements` - Per-tenant feature flags + limits
- `usage_records` - Metering for billing/limits
- `audit_logs` - Immutable audit trail
- `ai_usage_logs` - AI invocation ledger per blueprint

### CRM Models (Phase 2)
- `companies` - Accounts with attribution + AI fields
- `contacts` - People with opt-outs + attribution
- `leads` - Core sales object with AI scoring, qualification, conversion
- `pipelines` - Sales pipelines with stages
- `stages` - Pipeline stages with probability
- `deals` - Opportunities with forecasting
- `tasks` - Activities with reminders, recurrence
- `notes` - Polymorphic notes on leads/deals/contacts/companies
- `activities` - Complete timeline with AI attribution
- `proposals` - Proposal lifecycle per blueprint

### API Endpoints
| Module | Routes | Auth |
|--------|--------|------|
| Auth | `/api/v1/auth/register`, `/login`, `/google`, `/refresh`, `/me`, `/switch-tenant`, `/tenants` | Public/User |
| Tenants | `/api/v1/tenants/*` | Admin |
| Users | `/api/v1/users/*` | Manager+ |
| Contacts | `/api/v1/contacts/*` | Sales Executive+ |
| Companies | `/api/v1/companies/*` | Sales Executive+ |
| Leads | `/api/v1/leads/*` (assign, qualify, convert) | Sales Executive+ |
| Deals | `/api/v1/deals/*` + `/pipelines/*`, `/stages/*` | Sales Executive+ |
| Tasks | `/api/v1/tasks/*` | User |
| Notes | `/api/v1/notes/*` | User |
| Activities | `/api/v1/activities/*` | User |
| Health | `/health`, `/health/ready`, `/health/live` | Public |

## Getting Started

### Option 1: Docker (Recommended)
```bash
cd C:\Users\Globe\globexa_crm

# 1. Configure environment
copy .env.example .env
# Edit .env with your values (see Required Config below)

# 2. Start all services
docker-compose up -d

# 3. Run migrations
docker-compose exec api alembic upgrade head

# 4. Access API
# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
# Flower: http://localhost:5555
```

### Option 2: Local Development
```bash
cd C:\Users\Globe\globexa_crm

# 1. Install dependencies
pip install -e ".[dev]"

# 2. Configure environment
copy .env.example .env
# Edit .env with your values

# 3. Start PostgreSQL & Redis (required)
# Option A: Docker
docker run -d --name globexa-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=globexa_crm -p 5432:5432 postgres:16-alpine
docker run -d --name globexa-redis -p 6379:6379 redis:7-alpine

# Option B: Local installations

# 4. Run migrations
alembic upgrade head

# 5. Start services (in separate terminals)
# Terminal 1: API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Celery Worker
celery -A app.workers.celery_app worker --loglevel=info --queues=emails,campaigns,ai,integrations,usage

# Terminal 3: Celery Beat
celery -A app.workers.celery_app beat --loglevel=info

# Terminal 4: Flower (optional)
celery -A app.workers.celery_app flower --port=5555
```

## Required Configuration (.env)

```bash
# Required - Generate with: openssl rand -hex 32
SECRET_KEY=your-32-char-minimum-secret-key

# Database (adjust for your setup)
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_USERNAME=postgres
DATABASE_PASSWORD=postgres
DATABASE_NAME=globexa_crm

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# NVIDIA NIM API Key (for cloud AI)
# Get from: https://build.nvidia.com/
NVIDIA_API_KEY=your-nvidia-api-key

# Google OAuth (optional - for Google login)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Resend API Key (optional - for email)
RESEND_API_KEY=your-resend-api-key

# Ollama (optional - for local AI)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=llama3.2:3b
```

## Testing the API

### 1. Register a User
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "securepassword123",
    "full_name": "Admin User",
    "tenant_name": "My Company"
  }'
```

### 2. Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=securepassword123"
```

### 3. Use Access Token
```bash
# Replace YOUR_TOKEN with the access_token from login
curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer ${YOUR_TOKEN}"
```

### 4. Create a Contact
```bash
curl -X POST http://localhost:8000/api/v1/contacts \
  -H "Authorization: Bearer ${YOUR_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "+1-555-123-4567",
    "title": "CTO"
  }'
```

### 5. Create a Lead
```bash
curl -X POST http://localhost:8000/api/v1/leads \
  -H "Authorization: Bearer ${YOUR_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New CRM Inquiry",
    "description": "Interested in AI CRM",
    "source": "website",
    "status": "new"
  }'
```

## Key Features to Test

### Tenant Isolation
- Create second user → gets own tenant
- Try accessing first tenant's data with second user's token → 403/404

### RBAC
- Owner/Admin can manage users, tenants, settings
- Sales Manager sees team data
- Sales Executive only sees assigned leads/deals
- Marketing sees campaigns + permitted contacts

### Feature Entitlements
```bash
# Check tenant features
curl -X GET http://localhost:8000/api/v1/tenants/me \
  -H "Authorization: Bearer ${YOUR_TOKEN}"

# Admin can enable features
curl -X POST http://localhost:8000/api/v1/tenants/{tenant_id}/entitlements \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"feature_key": "ai_scoring", "enabled": true, "limit_value": 10000}'
```

### AI Router (via Celery tasks)
```python
# In Python shell or worker
from app.workers.tasks.ai_tasks_v2 import ai_score_lead_task
result = ai_score_lead_task.delay(
    tenant_id="...", 
    user_id="...", 
    lead_data={"company": "Acme Corp", "title": "CTO", "industry": "tech"}
)
print(result.get())
```

## Project Structure Summary
```
globexa_crm/
├── app/
│   ├── api/v1/           # 10 route modules
│   ├── core/             # Config, DB, Security
│   ├── middleware/       # Tenant resolution
│   ├── models/           # 17 SQLAlchemy models
│   ├── schemas/          # 50+ Pydantic schemas
│   ├── services/         # Auth, AI Router
│   ├── workers/          # Celery + 5 task modules
│   └── main.py           # FastAPI app
├── alembic/              # 2 migrations
├── tests/                # 3 test modules
├── docker-compose.yml    # Full stack
├── Dockerfile            # Container build
├── Makefile              # Dev commands
├── config.yaml           # Full configuration
└── pyproject.toml        # Dependencies
```

## Next Steps (Phase 3+)
1. **Campaign Engine** - Broadcast, sequences, triggered campaigns
2. **Email Provider Abstraction** - Resend, Gmail, Microsoft, SMTP
3. **Lead Source Integrations** - Meta, Google Ads, LinkedIn, Apollo, WhatsApp
4. **AI Sales Agent** - Auto-assignment, next-best-action, reply analysis
5. **AI Lead Miner** - ICP-based prospecting
6. **Proposal Generator** - AI-powered proposals
7. **In-CRM AI Assistant** - Tool-calling chat interface
8. **Billing/Subscriptions** - Stripe integration
9. **White-label** - Custom domains, branding

## Troubleshooting

### Common Issues
| Issue | Solution |
|-------|----------|
| `alembic: command not found` | Use `python -m alembic` or install in PATH |
| `ModuleNotFoundError` | Run `pip install -e ".[dev]"` |
| Database connection failed | Ensure PostgreSQL running on port 5432 |
| Redis connection failed | Ensure Redis running on port 6379 |
| JWT errors | Check SECRET_KEY is 32+ chars in .env |
| Google OAuth fails | Verify GOOGLE_CLIENT_ID/SECRET and redirect URI |

### Logs
```bash
# API logs
docker-compose logs -f api

# Worker logs
docker-compose logs -f worker

# All logs
docker-compose logs -f
```

---

**Ready to build Phase 3!** The foundation is solid with multi-tenancy, auth, RBAC, CRM models, and AI Router all working. Next up: Campaign Engine + Email Provider Abstraction.