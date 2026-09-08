# Globexa CRM

Multi-tenant AI-powered Sales CRM built with FastAPI, SQLAlchemy, Celery, and Next.js.

Checkpoint 4 connects the approved UI Lab to the authenticated CRM backend. See the [frontend setup and security guide](frontend/README.md), [Checkpoint 4 implementation report](CHECKPOINT_4_REPORT.md), [frontend audit](CHECKPOINT_4_FRONTEND_AUDIT.md) and [requirement traceability](CHECKPOINT_4_TRACEABILITY.md) for implementation details, verification and capability limits.

## Features

- **Multi-tenancy**: Secure tenant isolation with row-level security
- **Authentication**: JWT + Google OAuth with role-based access control
- **Package-based entitlements**: Flexible feature flags and limits (not hard-coded)
- **AI Router**: Local (Ollama) + Cloud (NVIDIA NIM, OpenAI, Anthropic) with usage ledger
- **Background Workers**: Celery + Redis for campaigns, AI jobs, integrations
- **Email Provider Abstraction**: Resend, Gmail, Microsoft Graph, SMTP
- **Frontend**: Next.js 16.3.3 + React 19.2.8 + TypeScript + Tailwind CSS + TanStack Query, with shared accessible CRM components
- **Browser sessions**: Opaque HttpOnly cookies backed by encrypted Redis sessions; backend tokens remain on the server

## Quick Start

### Backend services with Docker Compose

```bash
# Copy environment file
cp .env.example .env
# Edit .env with your values (especially SECRET_KEY)

# Start the backend and its supporting services
docker-compose up -d

# Access:
# API: http://localhost:8000
# API Docs: http://localhost:8000/docs
# Flower: http://localhost:5555
```

Compose defines the backend, PostgreSQL, Redis and workers. Start the Next.js frontend separately using the instructions below. For the reproducible Checkpoint 4 integration environment, including restricted database access and test provider adapters, follow the [frontend testing guide](frontend/README.md#reproducible-browser-integration-environment).

### Local Development

#### Backend
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

#### Frontend

Use Node.js 24 and a migrated Checkpoint 4 backend. Configure the server-only BFF environment before starting Next.js:

```bash
cd frontend

# Install the locked dependencies and create private local configuration
npm ci
cp .env.example .env.local
```

Set these values in `frontend/.env.local` for local HTTP development:

```dotenv
APP_ORIGIN=http://127.0.0.1:3000
BACKEND_API_URL=http://127.0.0.1:8000
FRONTEND_REDIS_URL=redis://127.0.0.1:6379/13
SESSION_ENCRYPTION_KEY=<private 64-character hexadecimal key>
FRONTEND_ENV=testing
```

Generate the session key with `openssl rand -hex 32` and store it privately. Both origins must omit a trailing slash and path; the backend origin must omit `/api/v1`. Never expose these variables through a `NEXT_PUBLIC_` prefix.

```bash
# Start local development at http://127.0.0.1:3000
npm run dev -- --hostname 127.0.0.1 --port 3000

# Build and start the production server
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

For production, use an HTTPS `APP_ORIGIN`, omit `FRONTEND_ENV`, and supply the same private encryption key to all frontend instances. The Node.js server must reach the backend and dedicated session Redis database. Production cookies require HTTPS. Sign in with a provisioned backend account; local/CI fixtures are created only by the separate testing bootstrap. See [frontend/README.md](frontend/README.md) for complete setup, authentication and test commands.

## Project Structure

```
globexa_crm/
├── app/                    # FastAPI backend
│   ├── api/v1/            # API routes
│   ├── core/              # Config, database, security
│   ├── middleware/        # Tenant middleware
│   ├── models/            # SQLAlchemy models
│   ├── schemas/           # Pydantic schemas
│   ├── services/          # Business logic
│   ├── workers/           # Celery tasks
│   └── main.py            # FastAPI app
├── alembic/               # Database migrations
├── frontend/              # Next.js frontend
│   ├── src/
│   │   ├── app/           # Login, protected CRM pages and API route handlers
│   │   │   └── api/       # Session and allowlisted CRM BFF routes
│   │   ├── api/           # Typed browser client and generated API contracts
│   │   ├── auth/          # Session provider and encrypted server session store
│   │   ├── components/    # Shared CRM views, dialogs and controls
│   │   ├── hooks/         # Queries and mutation state
│   │   ├── services/      # CRM DTO adapters and operations
│   │   └── types/         # Domain types
│   ├── tests/             # Unit and real-backend browser tests
│   ├── .env.example       # Server-only BFF environment template
│   ├── README.md          # Frontend setup, security and testing
│   └── package.json
├── tests/                 # Tests
├── config.yaml            # Configuration
├── pyproject.toml         # Python dependencies
├── docker-compose.yml     # Docker services
├── Dockerfile             # Backend Dockerfile
├── .env.example           # Environment template
└── README.md
```

## API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Frontend Pages

- **Command Center (`/`)** — Backend dashboard metrics and quick actions
- **Companies, Contacts and Leads** — Related CRM records, filters, forms and lead details
- **Pipeline (`/pipeline`)** — Deal board, stage changes and pipeline configuration
- **Customer 360 (`/customers/{kind}/{id}`)** — Related records, notes, activities and timeline
- **Tasks, Conversations and Campaigns** — Saved work and durable delivery/job outcomes
- **Automations and AI workspace** — Workflow operations and controlled AI requests
- **Integrations** — Provider availability, authorization and sync state
- **Analytics and Search** — Backend metrics and permission-aware results
- **Settings** — User profile, workspace details, team memberships and current plan
- **Help and Login** — Capability guidance and real backend sign-in

The sidebar workspace selector switches between authorized tenant memberships. Permissions control available actions, and the backend enforces every request. Provider features require backend configuration and entitlements; the [Checkpoint 4 report](CHECKPOINT_4_REPORT.md) distinguishes verified test-adapter behavior from live external delivery.

## Environment Variables

Key variables (see `.env.example` for full list):

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | JWT signing key (generate with `openssl rand -hex 32`) |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `NVIDIA_API_KEY` | NVIDIA NIM API key for AI |
| `OLLAMA_BASE_URL` | Local Ollama URL |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth secret |
| `RESEND_API_KEY` | Resend email API key |

The frontend uses its own server-only configuration in [frontend/.env.example](frontend/.env.example): `APP_ORIGIN`, `BACKEND_API_URL`, `FRONTEND_REDIS_URL` and `SESSION_ENCRYPTION_KEY`. The local HTTP exception is `FRONTEND_ENV=testing`; omit it in production. See the [frontend guide](frontend/README.md#configuration-and-startup).

## Development Commands

```bash
# Backend
make dev-install    # Install dev dependencies
make test           # Run tests
make lint           # Run linter
make format         # Format code
make typecheck      # Type checking
make db-upgrade     # Run migrations
make db-revision    # Create migration

# Frontend (in frontend/)
npm run dev         # Start dev server
npm run build       # Build for production
npm run start       # Start production server
npm run lint        # Run linter
npm run typecheck   # Generate route types and check TypeScript
npm run test:unit   # Unit tests; auth store tests require disposable Redis
npm run test:e2e    # Browser tests; start the isolated integration runtime first
```

## Docker Services

| Service | Port | Description |
|---------|------|-------------|
| postgres | 5432 | PostgreSQL database |
| redis | 6379 | Redis cache/broker |
| api | 8000 | FastAPI backend |
| worker | - | Celery worker |
| beat | - | Celery beat scheduler |
| flower | 5555 | Celery monitoring |

The frontend is started separately with Node.js; this Compose file does not define a frontend service.

## License

MIT
