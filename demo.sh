#!/usr/bin/env bash
# =============================================================================
# Globexa CRM - Demo Environment Setup Script
# Run this to spin up a complete demo environment with public URL via ngrok
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="${PROJECT_DIR}/demo_env"

# Demo configuration
DEMO_PORT=8000
NGROK_PORT=4040
DEMO_DB_NAME="globexa_crm_demo"
DEMO_REDIS_DB=1

print_header() {
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  ${GREEN}Globexa CRM - Demo Environment${NC}                              ${BLUE}║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo
}

print_step() {
    echo -e "${YELLOW}▶${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        print_error "$1 not found. Please install it first."
        return 1
    fi
    return 0
}

check_docker() {
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker daemon not running. Please start Docker Desktop."
        return 1
    fi
    return 0
}

cleanup() {
    echo
    print_step "Cleaning up demo environment..."
    
    # Stop ngrok
    if [ -n "${NGROK_PID:-}" ]; then
        kill $NGROK_PID 2>/dev/null || true
    fi
    
    # Stop docker compose
    if [ -f "${DEMO_DIR}/docker-compose.demo.yml" ]; then
        docker-compose -f "${DEMO_DIR}/docker-compose.demo.yml" down -v 2>/dev/null || true
    fi
    
    # Remove demo directory
    rm -rf "${DEMO_DIR}"
    
    print_success "Demo environment cleaned up"
    exit 0
}

trap cleanup INT TERM EXIT

main() {
    print_header
    
    print_step "Checking prerequisites..."
    
    check_command docker || exit 1
    check_command docker-compose || check_command "docker compose" || exit 1
    check_docker || exit 1
    
    # Check for ngrok (optional)
    if ! command -v ngrok &> /dev/null; then
        print_step "ngrok not found - installing..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            brew install ngrok 2>/dev/null || print_error "Please install ngrok manually: https://ngrok.com/download"
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            snap install ngrok 2>/dev/null || print_error "Please install ngrok manually: https://ngrok.com/download"
        else
            print_error "Please install ngrok manually: https://ngrok.com/download"
        fi
    fi
    
    print_success "Prerequisites checked"
    
    # Create demo directory
    print_step "Setting up demo environment..."
    rm -rf "${DEMO_DIR}"
    mkdir -p "${DEMO_DIR}"
    cd "${DEMO_DIR}"
    
    # Copy project files
    print_step "Copying project files..."
    cp -r "${PROJECT_DIR}"/* "${DEMO_DIR}"/ 2>/dev/null || true
    cp -r "${PROJECT_DIR}"/.env* "${DEMO_DIR}"/ 2>/dev/null || true
    cp -r "${PROJECT_DIR}"/.git* "${DEMO_DIR}"/ 2>/dev/null || true
    
    # Create demo-specific docker-compose
    print_step "Creating demo docker-compose..."
    cat > "${DEMO_DIR}/docker-compose.demo.yml" << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: globexa-demo-postgres
    environment:
      POSTGRES_USER: demo
      POSTGRES_PASSWORD: demo
      POSTGRES_DB: globexa_crm_demo
    ports:
      - "5432:5432"
    volumes:
      - demo_postgres_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init-db.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U demo"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    container_name: globexa-demo-redis
    ports:
      - "6379:6379"
    volumes:
      - demo_redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10

  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: globexa-demo-api
    environment:
      - APP_ENV=demo
      - APP_DEBUG=true
      - DATABASE_HOST=postgres
      - DATABASE_PORT=5432
      - DATABASE_USERNAME=demo
      - DATABASE_PASSWORD=demo
      - DATABASE_NAME=globexa_crm_demo
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_DB=1
      - SECRET_KEY=demo-secret-key-for-testing-only-32-chars-min
      - NVIDIA_API_KEY=${NVIDIA_API_KEY:-}
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID:-}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET:-}
      - RESEND_API_KEY=${RESEND_API_KEY:-}
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - .:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: globexa-demo-worker
    environment:
      - APP_ENV=demo
      - DATABASE_HOST=postgres
      - DATABASE_PORT=5432
      - DATABASE_USERNAME=demo
      - DATABASE_PASSWORD=demo
      - DATABASE_NAME=globexa_crm_demo
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_DB=1
      - SECRET_KEY=demo-secret-key-for-testing-only-32-chars-min
      - NVIDIA_API_KEY=${NVIDIA_API_KEY:-}
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - .:/app
    command: celery -A app.workers.celery_app worker --loglevel=info --queues=emails,campaigns,ai,integrations,usage

  beat:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: globexa-demo-beat
    environment:
      - APP_ENV=demo
      - DATABASE_HOST=postgres
      - DATABASE_PORT=5432
      - DATABASE_USERNAME=demo
      - DATABASE_PASSWORD=demo
      - DATABASE_NAME=globexa_crm_demo
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_DB=1
      - SECRET_KEY=demo-secret-key-for-testing-only-32-chars-min
      - NVIDIA_API_KEY=${NVIDIA_API_KEY:-}
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - .:/app
    command: celery -A app.workers.celery_app beat --loglevel=info

volumes:
  demo_postgres_data:
  demo_redis_data:
EOF

    # Create demo environment file
    print_step "Creating demo environment..."
    cat > "${DEMO_DIR}/.env.demo" << 'EOF'
# Demo Environment Configuration
APP_ENV=demo
APP_DEBUG=true
APP_HOST=0.0.0.0
APP_PORT=8000

DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_USERNAME=demo
DATABASE_PASSWORD=demo
DATABASE_NAME=globexa_crm_demo

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=1

SECRET_KEY=demo-secret-key-for-testing-only-32-chars-minimum
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=30

# Add your NVIDIA API key here for AI features
NVIDIA_API_KEY=

# Optional: Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Optional: Resend for emails
RESEND_API_KEY=

# Local Ollama (if running locally)
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_DEFAULT_MODEL=llama3.2:3b
EOF

    # Create demo seed script
    print_step "Creating demo data seed script..."
    cat > "${DEMO_DIR}/demo_seed.py" << 'EOF'
#!/usr/bin/env python3
"""Demo data seed script for Globexa CRM."""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from app.core.database import AsyncSessionLocal
from app.models import (
    Lead, Contact, Company, Deal, Pipeline, Stage, Task, Note, Activity,
    LeadSourceEnum, LeadStatusEnum, TaskStatusEnum, TaskPriorityEnum,
    ActivityTypeEnum, DealStageEnum
)
from app.core.security import hash_password

async def seed():
    async with AsyncSessionLocal() as db:
        print("🌱 Seeding demo data...")
        
        # Create demo tenant
        from app.models import Tenant, User, Membership, RoleEnum, Subscription, SubscriptionStatusEnum, PackageEnum
        
        tenant = Tenant(
            name="Globexa Demo",
            slug="globexa-demo",
            is_active=True,
        )
        db.add(tenant)
        await db.flush()
        
        # Create demo user
        user = User(
            email="demo@globexa.com",
            hashed_password=hash_password("demo123"),
            full_name="Demo User",
            is_active=True,
            email_verified=True,
        )
        db.add(user)
        await db.flush()
        
        # Create membership
        membership = Membership(
            user_id=user.id,
            tenant_id=tenant.id,
            role=RoleEnum.OWNER,
            is_default=True,
        )
        db.add(membership)
        
        # Create subscription
        subscription = Subscription(
            tenant_id=tenant.id,
            package=PackageEnum.AI_PRO,
            status=SubscriptionStatusEnum.ACTIVE,
        )
        db.add(subscription)
        
        # Create pipeline
        pipeline = Pipeline(
            tenant_id=tenant.id,
            name="Sales Pipeline",
            description="Default sales pipeline",
            is_default=True,
            is_active=True,
        )
        db.add(pipeline)
        await db.flush()
        
        # Create stages
        stages = [
            Stage(tenant_id=tenant.id, pipeline_id=pipeline.id, name="Prospecting", order=0, probability=10, color="#6366f1"),
            Stage(tenant_id=tenant.id, pipeline_id=pipeline.id, name="Qualification", order=1, probability=25, color="#06b6d4"),
            Stage(tenant_id=tenant.id, pipeline_id=pipeline.id, name="Proposal", order=2, probability=50, color="#f59e0b"),
            Stage(tenant_id=tenant.id, pipeline_id=pipeline.id, name="Negotiation", order=3, probability=75, color="#ef4444"),
            Stage(tenant_id=tenant.id, pipeline_id=pipeline.id, name="Closed Won", order=4, probability=100, is_closed=True, is_won=True, color="#22c55e"),
            Stage(tenant_id=tenant.id, pipeline_id=pipeline.id, name="Closed Lost", order=5, probability=0, is_closed=True, is_won=False, color="#9ca3af"),
        ]
        for stage in stages:
            db.add(stage)
        await db.flush()
        
        # Create sample companies
        companies = []
        company_data = [
            ("Acme Corp", "acme.com", "SaaS", "51-200", 5000000, "San Francisco", "CA", "USA"),
            ("TechStart Inc", "techstart.io", "FinTech", "11-50", 1200000, "Austin", "TX", "USA"),
            ("Global Industries", "globalind.com", "Manufacturing", "1000+", 50000000, "Chicago", "IL", "USA"),
            ("HealthPlus", "healthplus.co", "Healthcare", "201-500", 8000000, "Boston", "MA", "USA"),
            ("EduTech Solutions", "edutech.ai", "EdTech", "11-50", 900000, "Seattle", "WA", "USA"),
        ]
        
        for name, domain, industry, size, revenue, city, state, country in company_data:
            company = Company(
                tenant_id=tenant.id,
                name=name,
                domain=domain,
                industry=industry,
                size=size,
                annual_revenue=revenue,
                city=city,
                state=state,
                country=country,
                source=LeadSourceEnum.WEBSITE,
            )
            db.add(company)
            companies.append(company)
        await db.flush()
        
        # Create contacts and leads
        lead_titles = [
            "Enterprise CRM Inquiry",
            "AI Sales Automation Demo Request",
            "Pricing for 50 Users",
            "Integration with Salesforce",
            "Migration from HubSpot",
            "Custom Reporting Needs",
            "API Access Request",
            "White-label Partnership",
            "Enterprise Security Audit",
            "Multi-tenant Setup",
        ]
        
        sources = [
            LeadSourceEnum.WEBSITE,
            LeadSourceEnum.LINKEDIN,
            LeadSourceEnum.GOOGLE_ADS,
            LeadSourceEnum.REFERRAL,
            LeadSourceEnum.META_LEAD_ADS,
        ]
        
        statuses = [
            LeadStatusEnum.NEW,
            LeadStatusEnum.CONTACTED,
            LeadStatusEnum.QUALIFIED,
            LeadStatusEnum.NURTURING,
        ]
        
        for i in range(10):
            # Create contact
            contact = Contact(
                tenant_id=tenant.id,
                company_id=companies[i % len(companies)].id,
                first_name=["John", "Sarah", "Mike", "Emily", "David", "Lisa", "James", "Amanda", "Robert", "Jennifer"][i],
                last_name=["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"][i],
                email=f"contact{i}@example.com",
                title=["CTO", "VP Sales", "CEO", "VP Marketing", "CTO", "VP Engineering", "CRO", "VP Growth", "CMO", "Head of Sales"][i],
                source=sources[i % len(sources)],
            )
            db.add(contact)
            await db.flush()
            
            # Create lead
            lead = Lead(
                tenant_id=tenant.id,
                contact_id=contact.id,
                company_id=contact.company_id,
                title=lead_titles[i],
                description=f"Demo lead {i+1} - interested in Globexa CRM features",
                status=statuses[i % len(statuses)],
                source=sources[i % len(sources)],
                ai_score=70 + (i * 3),
                ai_score_reason=f"Strong fit: {contact.title} at {companies[i % len(companies)].name}",
                is_qualified=i >= 3,
            )
            db.add(lead)
            await db.flush()
            
            # Create activity
            activity = Activity(
                tenant_id=tenant.id,
                lead_id=lead.id,
                contact_id=contact.id,
                company_id=contact.company_id,
                type=ActivityTypeEnum.LEAD_CREATED,
                subject=f"Lead created: {lead.title}",
                description=f"New lead from {lead.source.value}",
                is_ai_generated=False,
            )
            db.add(activity)
        
        # Create a few deals
        for i in range(3):
            lead = (await db.execute(
                select(Lead).where(Lead.tenant_id == tenant.id, Lead.is_qualified == True).limit(3).offset(i)
            )).scalar_one()
            
            deal = Deal(
                tenant_id=tenant.id,
                pipeline_id=pipeline.id,
                stage_id=stages[i + 1].id,
                contact_id=lead.contact_id,
                company_id=lead.company_id,
                lead_id=lead.id,
                title=f"Deal: {lead.title}",
                value=[5000000, 1200000, 2500000][i],
                currency="USD",
                probability=stages[i + 1].probability,
                expected_close_date=datetime.now(timezone.utc) + timedelta(days=30 + i * 15),
            )
            db.add(deal)
            await db.flush()
            
            # Update lead
            lead.converted_deal_id = deal.id
            lead.status = LeadStatusEnum.CONVERTED
            lead.converted_at = datetime.now(timezone.utc)
        
        # Create some tasks
        for i in range(5):
            task = Task(
                tenant_id=tenant.id,
                lead_id=(await db.execute(select(Lead).where(Lead.tenant_id == tenant.id).limit(5).offset(i))).scalar_one().id,
                title=["Follow up call", "Send proposal", "Schedule demo", "Technical review", "Contract review"][i],
                status=TaskStatusEnum.PENDING,
                priority=TaskPriorityEnum.HIGH if i < 2 else TaskPriorityEnum.MEDIUM,
                due_date=datetime.now(timezone.utc) + timedelta(days=i + 1),
            )
            db.add(task)
        
        await db.commit()
        print(f"✅ Demo data seeded for tenant: {tenant.slug}")
        print(f"📧 Demo login: demo@globexa.com / demo123")
        print(f"🏢 Created {len(companies)} companies, 10 contacts, 10 leads, 3 deals, 5 tasks")

if __name__ == "__main__":
    from app.core.database import init_db
    asyncio.run(init_db())
    asyncio.run(seed())
EOF

    chmod +x "${DEMO_DIR}/demo_seed.py"
    
    # Start services
    print_step "Starting Docker services..."
    cd "${DEMO_DIR}"
    docker-compose -f docker-compose.demo.yml up -d --build
    
    # Wait for services
    print_step "Waiting for services to be healthy..."
    sleep 10
    
    # Run migrations
    print_step "Running database migrations..."
    docker-compose -f docker-compose.demo.yml exec -T api alembic upgrade head
    
    # Seed demo data
    print_step "Seeding demo data..."
    docker-compose -f docker-compose.demo.yml exec -T api python demo_seed.py
    
    # Start ngrok
    print_step "Starting ngrok tunnel..."
    ngrok http ${DEMO_PORT} --log=stdout > "${DEMO_DIR}/ngrok.log" 2>&1 &
    NGROK_PID=$!
    
    # Wait for ngrok to start
    sleep 3
    
    # Get public URL
    NGROK_URL=$(curl -s http://localhost:${NGROK_PORT}/api/tunnels | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || echo "")
    
    # Success message
    echo
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}  ${GREEN}✅ DEMO ENVIRONMENT READY!${NC}                                    ${GREEN}║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo
    echo -e "  ${BLUE}🌐 Public URL:${NC}  ${GREEN}${NGROK_URL}${NC}"
    echo -e "  ${BLUE}📚 API Docs:${NC}     ${GREEN}${NGROK_URL}/docs${NC}"
    echo -e "  ${BLUE}🔐 Login:${NC}        ${GREEN}demo@globexa.com${NC} / ${GREEN}demo123${NC}"
    echo -e "  ${BLUE}📊 Health:${NC}       ${GREEN}${NGROK_URL}/health${NC}"
    echo
    echo -e "  ${YELLOW}Test API:${NC}"
    echo -e "    curl -X POST ${NGROK_URL}/api/v1/auth/login \\"
    echo -e "      -d 'username=demo@globexa.com&password=demo123'"
    echo
    echo -e "  ${YELLOW}AI Features (need NVIDIA_API_KEY in .env):${NC}"
    echo -e "    curl -X POST ${NGROK_URL}/api/v1/ai/leads/{lead_id}/score \\"
    echo -e "      -H 'Authorization: Bearer <token>' -d '{}'"
    echo
    echo -e "  ${YELLOW}Press Ctrl+C to stop demo${NC}"
    echo
    
    # Keep running
    wait $NGROK_PID
}

# Check if python3 is available for ngrok URL extraction
if ! command -v python3 &> /dev/null; then
    print_step "Installing python3 for ngrok URL extraction..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install python3
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        apt-get update && apt-get install -y python3
    fi
fi

main