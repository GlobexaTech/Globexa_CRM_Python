# Globexa CRM

Multi-tenant AI-powered Sales CRM built with FastAPI, SQLAlchemy, Celery, and Next.js.

## Features

- **Multi-tenancy**: Secure tenant isolation with row-level security
- **Authentication**: JWT + Google OAuth with role-based access control
- **Package-based entitlements**: Flexible feature flags and limits (not hard-coded)
- **AI Router**: Local (Ollama) + Cloud (NVIDIA NIM, OpenAI, Anthropic) with usage ledger
- **Background Workers**: Celery + Redis for campaigns, AI jobs, integrations
- **Email Provider Abstraction**: Resend, Gmail, Microsoft Graph, SMTP
- **Modern Frontend**: Next.js 14 + TypeScript + Tailwind CSS + shadcn/ui

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Copy environment file
cp .env.example .env
# Edit .env with your values (especially SECRET_KEY)

# Start all services
docker-compose up -d

# Access:
# Frontend: http://localhost:3000
# API: http://localhost:8000
# API Docs: http://localhost:8000/docs
# Flower: http://localhost:5555
```

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
```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
npm start
```

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
│   │   ├── app/           # App Router pages
│   │   │   ├── (auth)/    # Login, register
│   │   │   └── (dashboard)/ # Protected pages
│   │   ├── components/    # React components
│   │   │   └── ui/        # shadcn/ui components
│   │   └── lib/           # Utilities, API client, auth
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

- **Dashboard** - Overview with stats and quick actions
- **Companies** - Manage company accounts
- **Contacts** - Manage contacts and relationships
- **Leads** - Track and qualify sales opportunities
- **Deals** - Pipeline management (Kanban + Table views)
- **Pipelines** - Configure sales pipelines and stages
- **Tenants** - Multi-tenant management (admin)
- **Settings** - User profile, security, notifications, appearance

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
| frontend | 3000 | Next.js frontend |

## License

MIT