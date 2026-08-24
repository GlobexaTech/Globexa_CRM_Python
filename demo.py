#!/usr/bin/env python3
# =============================================================================
# Globexa CRM - Demo Environment Setup (Cross-platform Python version)
# Run: python demo.py
# =============================================================================

import os
import sys
import subprocess
import time
import signal
import atexit
import shutil
import json
from pathlib import Path
from typing import Optional

# Colors
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'

class DemoManager:
    def __init__(self):
        self.project_dir = Path(__file__).parent.absolute()
        self.demo_dir = self.project_dir / "demo_env"
        self.ngrok_process: Optional[subprocess.Popen] = None
        self.docker_compose_process: Optional[subprocess.Popen] = None
        
    def print_header(self):
        print(f"{Colors.BLUE}{'='*70}{Colors.NC}")
        print(f"{Colors.BLUE}  {Colors.GREEN}Globexa CRM - Demo Environment{Colors.NC}")
        print(f"{Colors.BLUE}{'='*70}{Colors.NC}")
        print()
    
    def print_step(self, msg: str):
        print(f"{Colors.YELLOW}▶{Colors.NC} {msg}")
    
    def print_success(self, msg: str):
        print(f"{Colors.GREEN}✓{Colors.NC} {msg}")
    
    def print_error(self, msg: str):
        print(f"{Colors.RED}✗{Colors.NC} {msg}")
    
    def run_cmd(self, cmd: list, cwd: Optional[Path] = None, capture: bool = False) -> subprocess.CompletedProcess:
        """Run command and return result."""
        result = subprocess.run(
            cmd,
            cwd=cwd or self.demo_dir,
            capture_output=capture,
            text=True
        )
        if result.returncode != 0 and not capture:
            self.print_error(f"Command failed: {' '.join(cmd)}")
            if result.stderr:
                print(result.stderr)
        return result
    
    def check_prerequisites(self) -> bool:
        """Check Docker, Docker Compose, and ngrok."""
        self.print_step("Checking prerequisites...")
        
        # Check Docker
        if not shutil.which("docker"):
            self.print_error("Docker not found. Install from https://docker.com")
            return False
        
        # Check Docker daemon
        result = self.run_cmd(["docker", "info"], capture=True)
        if result.returncode != 0:
            self.print_error("Docker daemon not running. Start Docker Desktop.")
            return False
        
        # Check Docker Compose
        compose_cmd = None
        if shutil.which("docker-compose"):
            compose_cmd = ["docker-compose"]
        else:
            result = self.run_cmd(["docker", "compose", "version"], capture=True)
            if result.returncode == 0:
                compose_cmd = ["docker", "compose"]
        
        if not compose_cmd:
            self.print_error("Docker Compose not found")
            return False
        
        self.compose_cmd = compose_cmd
        self.print_success("Docker & Docker Compose ready")
        
        # Check ngrok
        if not shutil.which("ngrok"):
            self.print_step("ngrok not found. You can:")
            print("  1. Install from https://ngrok.com/download")
            print("  2. Or run without ngrok (local only)")
            self.ngrok_available = False
        else:
            self.ngrok_available = True
            self.print_success("ngrok found")
        
        return True
    
    def setup_demo_dir(self):
        """Create demo directory and files."""
        self.print_step("Setting up demo environment...")
        
        # Clean previous demo
        if self.demo_dir.exists():
            shutil.rmtree(self.demo_dir)
        
        self.demo_dir.mkdir(parents=True)
        
        # Copy project files
        self.print_step("Copying project files...")
        for item in self.project_dir.iterdir():
            if item.name in {'.git', '__pycache__', '.pytest_cache', 'demo_env', '*.egg-info', 'dist', 'build', '.venv', 'venv'}:
                continue
            if item.is_dir():
                shutil.copytree(item, self.demo_dir / item.name, dirs_exist_ok=True)
            else:
                shutil.copy2(item, self.demo_dir / item.name)
        
        # Create demo docker-compose
        self.create_docker_compose()
        
        # Create .env.demo
        self.create_env_demo()
        
        # Create seed script
        self.create_seed_script()
        
        self.print_success("Demo environment created")
    
    def create_docker_compose(self):
        """Create demo-specific docker-compose.yml"""
        compose_content = '''version: '3.8'

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
'''
        (self.demo_dir / "docker-compose.demo.yml").write_text(compose_content)
        
        # Also create .env.demo
        env_content = '''# Demo Environment Configuration
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
'''
        (self.demo_dir / ".env.demo").write_text(env_content)
    
    def create_seed_script(self):
        """Create demo seed script."""
        seed_content = '''#!/usr/bin/env python3
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
        
        from app.models import Tenant, User, Membership, RoleEnum, Subscription, SubscriptionStatusEnum, PackageEnum
        
        tenant = Tenant(
            name="Globexa Demo",
            slug="globexa-demo",
            is_active=True,
        )
        db.add(tenant)
        await db.flush()
        
        user = User(
            email="demo@globexa.com",
            hashed_password=hash_password("demo123"),
            full_name="Demo User",
            is_active=True,
            email_verified=True,
        )
        db.add(user)
        await db.flush()
        
        membership = Membership(
            user_id=user.id,
            tenant_id=tenant.id,
            role=RoleEnum.OWNER,
            is_default=True,
        )
        db.add(membership)
        
        subscription = Subscription(
            tenant_id=tenant.id,
            package=PackageEnum.AI_PRO,
            status=SubscriptionStatusEnum.ACTIVE,
        )
        db.add(subscription)
        
        pipeline = Pipeline(
            tenant_id=tenant.id,
            name="Sales Pipeline",
            description="Default sales pipeline",
            is_default=True,
            is_active=True,
        )
        db.add(pipeline)
        await db.flush()
        
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
        
        company_data = [
            ("Acme Corp", "acme.com", "SaaS", "51-200", 5000000, "San Francisco", "CA", "USA"),
            ("TechStart Inc", "techstart.io", "FinTech", "11-50", 1200000, "Austin", "TX", "USA"),
            ("Global Industries", "globalind.com", "Manufacturing", "1000+", 50000000, "Chicago", "IL", "USA"),
            ("HealthPlus", "healthplus.co", "Healthcare", "201-500", 8000000, "Boston", "MA", "USA"),
            ("EduTech Solutions", "edutech.ai", "EdTech", "11-50", 900000, "Seattle", "WA", "USA"),
        ]
        
        companies = []
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
        
        lead_titles = [
            "Enterprise CRM Inquiry", "AI Sales Automation Demo Request",
            "Pricing for 50 Users", "Integration with Salesforce",
            "Migration from HubSpot", "Custom Reporting Needs",
            "API Access Request", "White-label Partnership",
            "Enterprise Security Audit", "Multi-tenant Setup",
        ]
        
        sources = [
            LeadSourceEnum.WEBSITE, LeadSourceEnum.LINKEDIN,
            LeadSourceEnum.GOOGLE_ADS, LeadSourceEnum.REFERRAL,
            LeadSourceEnum.META_LEAD_ADS,
        ]
        
        statuses = [
            LeadStatusEnum.NEW, LeadStatusEnum.CONTACTED,
            LeadStatusEnum.QUALIFIED, LeadStatusEnum.NURTURING,
        ]
        
        for i in range(10):
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
        
        for i in range(3):
            lead = (await db.execute(
                __import__('sqlalchemy').select(Lead).where(
                    Lead.tenant_id == tenant.id, Lead.is_qualified == True
                ).limit(3).offset(i)
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
            
            lead.converted_deal_id = deal.id
            lead.status = LeadStatusEnum.CONVERTED
            lead.converted_at = datetime.now(timezone.utc)
        
        for i in range(5):
            task = Task(
                tenant_id=tenant.id,
                lead_id=(await db.execute(
                    __import__('sqlalchemy').select(Lead).where(Lead.tenant_id == tenant.id).limit(5).offset(i)
                )).scalar_one().id,
                title=["Follow up call", "Send proposal", "Schedule demo", "Technical review", "Contract review"][i],
                status=TaskStatusEnum.PENDING,
                priority=TaskPriorityEnum.HIGH if i < 2 else TaskPriorityEnum.MEDIUM,
                due_date=datetime.now(timezone.utc) + timedelta(days=i + 1),
            )
            db.add(task)
        
        await db.commit()
        print(f"✅ Demo data seeded for tenant: {tenant.slug}")
        print(f"📧 Demo login: demo@globexa.com / demo123")

if __name__ == "__main__":
    from app.core.database import init_db
    asyncio.run(init_db())
    asyncio.run(seed())
'''
        (self.demo_dir / "demo_seed.py").write_text(seed_content)
    
    def start_services(self) -> bool:
        """Start Docker services."""
        self.print_step("Starting Docker services...")
        
        # Build and start
        result = self.run_cmd(self.compose_cmd + ["-f", "docker-compose.demo.yml", "up", "-d", "--build"])
        if result.returncode != 0:
            self.print_error("Failed to start Docker services")
            return False
        
        # Wait for health
        self.print_step("Waiting for services to be healthy...")
        for i in range(30):
            time.sleep(2)
            # Check health
            result = self.run_cmd(["docker", "ps", "--filter", "name=globexa-demo", "--format", "{{.Status}}"], capture=True)
            if "healthy" in result.stdout or "Up" in result.stdout:
                pass
        
        self.print_success("Docker services started")
        return True
    
    def run_migrations(self) -> bool:
        """Run database migrations."""
        self.print_step("Running database migrations...")
        
        result = self.run_cmd(
            self.compose_cmd + ["-f", "docker-compose.demo.yml", "exec", "-T", "api", "alembic", "upgrade", "head"],
            capture=True
        )
        
        if result.returncode != 0:
            self.print_error(f"Migration failed: {result.stderr}")
            return False
        
        self.print_success("Migrations complete")
        return True
    
    def seed_data(self) -> bool:
        """Seed demo data."""
        self.print_step("Seeding demo data...")
        
        result = self.run_cmd(
            self.compose_cmd + ["-f", "docker-compose.demo.yml", "exec", "-T", "api", "python", "demo_seed.py"],
            capture=True
        )
        
        if result.returncode != 0:
            self.print_error(f"Seed failed: {result.stderr}")
            return False
        
        self.print_success("Demo data seeded")
        return True
    
    def start_ngrok(self) -> Optional[str]:
        """Start ngrok tunnel and return public URL."""
        if not self.ngrok_available:
            self.print_step("ngrok not available - demo running locally at http://localhost:8000")
            return "http://localhost:8000"
        
        self.print_step("Starting ngrok tunnel...")
        
        # Start ngrok
        self.ngrok_process = subprocess.Popen(
            ["ngrok", "http", "8000", "--log", "stdout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for ngrok to start
        time.sleep(3)
        
        # Get public URL from ngrok API
        try:
            import urllib.request
            with urllib.request.urlopen("http://localhost:4040/api/tunnels") as response:
                data = json.load(response)
                public_url = data['tunnels'][0]['public_url']
                self.print_success(f"ngrok tunnel active: {public_url}")
                return public_url
        except Exception as e:
            self.print_error(f"Could not get ngrok URL: {e}")
            return "http://localhost:8000"
    
    def cleanup(self):
        """Clean up processes."""
        self.print_step("Cleaning up...")
        
        if self.ngrok_process:
            self.ngrok_process.terminate()
            try:
                self.ngrok_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.ngrok_process.kill()
        
        # Stop docker
        self.run_cmd(self.compose_cmd + ["-f", "docker-compose.demo.yml", "down", "-v"])
        
        self.print_success("Cleanup complete")
    
    def run(self):
        """Main entry point."""
        self.print_header = lambda: print(f"""
{Colors.BLUE}{'='*70}{Colors.NC}
{Colors.BLUE}  {Colors.GREEN}Globexa CRM - Demo Environment{Colors.NC}
{Colors.BLUE}{'='*70}{Colors.NC}
""")
        self.print_header()
        
        # Register cleanup
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
        signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
        
        # Run steps
        if not self.check_prerequisites():
            sys.exit(1)
        
        self.setup_demo_dir()
        
        if not self.start_services():
            sys.exit(1)
        
        if not self.run_migrations():
            sys.exit(1)
        
        if not self.seed_data():
            sys.exit(1)
        
        public_url = self.start_ngrok()
        
        # Success message
        print(f"""
{Colors.GREEN}{'='*70}{Colors.NC}
{Colors.BLUE}  {Colors.GREEN}✅ DEMO ENVIRONMENT READY!{Colors.NC}
{Colors.GREEN}{'='*70}{Colors.NC}

  {Colors.BLUE}🌐 Public URL:{Colors.NC}  {Colors.GREEN}{public_url}{Colors.NC}
  {Colors.BLUE}📚 API Docs:{Colors.NC}     {Colors.GREEN}{public_url}/docs{Colors.NC}
  {Colors.BLUE}🔐 Login:{Colors.NC}        {Colors.GREEN}demo@globexa.com{Colors.NC} / {Colors.GREEN}demo123{Colors.NC}
  {Colors.BLUE}📊 Health:{Colors.NC}       {Colors.GREEN}{public_url}/health{Colors.NC}

  {Colors.YELLOW}Test API:{Colors.NC}
    curl -X POST {public_url}/api/v1/auth/login \\
      -d 'username=demo@globexa.com&password=demo123'

  {Colors.YELLOW}AI Features (add NVIDIA_API_KEY to .env for full AI):{Colors.NC}
    curl -X POST {public_url}/api/v1/ai/leads/{{lead_id}}/score \\
      -H 'Authorization: Bearer <token>' -d '{{}}'

  {Colors.YELLOW}Press Ctrl+C to stop demo{Colors.NC}
""")
        
        # Keep running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print()
            self.cleanup()


def main():
    manager = DemoManager()
    manager.run()


if __name__ == "__main__":
    main()