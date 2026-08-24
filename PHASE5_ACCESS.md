# Phase 5 Complete - AI Sales Agent Access Instructions

## Project Location
```
C:\Users\Globe\globexa_crm\
```

## What's Built (Phase 5 - AI Sales Agent)

### AI Services (7 Core Services)

| Service | Capability | Key Features |
|---------|------------|--------------|
| **LeadScoringService** | Explainable lead scoring | Rule-based + AI hybrid, factor breakdown, confidence scoring, recommended actions |
| **AutoAssignmentService** | Hybrid lead assignment | Industry expertise, territory, workload, conversion rate, AI recommendation |
| **NextBestActionService** | Next-best-action engine | Call/email/demo/proposal/nurture with timeline, priority, confidence |
| **ReplyAnalysisService** | Reply analysis & response | Intent classification, sentiment, purchase probability, auto-response generation |
| **LeadMinerService** | ICP-based prospecting | AI search, enrichment, scoring ≥85, auto-lead creation |
| **ProposalGeneratorService** | AI proposal generation | Executive summary, pricing, terms, section regeneration |
| **AIAssistantService** | In-CRM chat assistant | 12 tools, permission-gated, tool calling, conversation history |

### AI Router (Foundation)
- **Local (Ollama)**: Classification, scoring, extraction, summarization, intent, tagging, routing
- **Cloud (NVIDIA NIM/OpenAI/Anthropic)**: Lead scoring, personalization, campaigns, proposals, reply analysis, next-best-action, lead mining, research, chat assistant
- **Usage Ledger**: Every invocation logged (tenant, user, task, provider, model, tokens, cost, latency, success, tools)

### API Endpoints (All under `/api/v1/ai/`)

| Endpoint | Method | Permission | Description |
|----------|--------|------------|-------------|
| `/leads/{lead_id}/score` | POST | `ai:score_leads` | Score lead with explainable factors |
| `/leads/{lead_id}/assign` | POST | `leads:write` + `ai:assign_leads` | Auto-assign to best salesperson |
| `/leads/{lead_id}/next-action` | POST | `leads:read` | Get next best action recommendation |
| `/leads/{lead_id}/analyze-reply` | POST | `leads:read` | Analyze inbound reply intent/sentiment |
| `/leads/{lead_id}/generate-response` | POST | `leads:write` + `ai:respond_email` | Generate reply response |
| `/lead-miner/run` | POST | `ai:score_leads` | Run ICP-based lead mining |
| `/deals/{deal_id}/generate-proposal` | POST | `deals:write` | Generate AI proposal |
| `/proposals/{proposal_id}/regenerate` | POST | `deals:write` | Regenerate proposal section |
| `/chat` | POST | `ai:chat` | Chat with AI assistant (12 tools) |
| `/leads/batch-score` | POST | `ai:score_leads` | Batch score multiple leads |
| `/leads/batch-assign` | POST | `leads:write` | Batch auto-assign leads |
| `/usage/analytics` | GET | `ai:chat` | AI usage analytics (cost, tokens, latency) |

### RBAC - Fine-Grained AI Permissions

| Role | AI Permissions |
|------|----------------|
| **Viewer** | None |
| **Sales Executive** | `ai:read_leads`, `ai:score_leads`, `ai:assign_leads`, `ai:draft_email`, `ai:send_email`, `ai:read_replies`, `ai:respond_email`, `ai:create_proposal`, `ai:change_stage`, `ai:chat` |
| **Marketing** | `ai:read_leads`, `ai:draft_email`, `ai:chat` + feature flags |
| **Sales Manager** | All Sales Executive + `ai:schedule_email` |
| **Admin** | All AI permissions + feature flags |
| **Owner** | All permissions |

### Feature Entitlements (Per-Tenant, Not Hard-Coded)
- `feature:ai_scoring` - Enable lead scoring
- `feature:ai_miner` - Enable lead miner
- `feature:campaigns` - Enable campaigns
- `feature:whatsapp` - Enable WhatsApp
- `feature:api` - Enable API access

## Getting Started

### 1. Run Migration
```bash
cd C:\Users\Globe\globexa_crm
alembic upgrade head
```

### 2. Configure AI Providers (.env)
```bash
# NVIDIA NIM (Primary Cloud)
NVIDIA_API_KEY=your-nvidia-key

# Optional: Local Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=llama3.2:3b

# Optional: Other Cloud Providers
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
```

### 3. Enable AI Features for Tenant
```bash
# As admin, enable AI features for tenant
curl -X POST http://localhost:8000/api/v1/tenants/{tenant_id}/entitlements \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"feature_key": "ai_scoring", "enabled": true, "limit_value": 10000}'

curl -X POST http://localhost:8000/api/v1/tenants/{tenant_id}/entitlements \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"feature_key": "ai_miner", "enabled": true, "limit_value": 5000}'

curl -X POST http://localhost:8000/api/v1/tenants/{tenant_id}/entitlements \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"feature_key": "campaigns", "enabled": true}'
```

### 4. Start Services
```bash
# API
uvicorn app.main:app --reload

# Celery Workers (needed for AI batch tasks)
celery -A app.workers.celery_app worker --loglevel=info --queues=ai,campaigns,emails,integrations,usage

# Celery Beat (scheduled AI tasks)
celery -A app.workers.celery_app beat --loglevel=info
```

## Test AI Capabilities

### 1. Score a Lead
```bash
curl -X POST http://localhost:8000/api/v1/ai/leads/{lead_id}/score \
  -H "Authorization: Bearer SALES_EXEC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 2. Auto-Assign Lead
```bash
curl -X POST http://localhost:8000/api/v1/ai/leads/{lead_id}/assign \
  -H "Authorization: Bearer SALES_EXEC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 3. Get Next Best Action
```bash
curl -X POST http://localhost:8000/api/v1/ai/leads/{lead_id}/next-action \
  -H "Authorization: Bearer SALES_EXEC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 4. Analyze Reply
```bash
curl -X POST http://localhost:8000/api/v1/ai/leads/{lead_id}/analyze-reply \
  -H "Authorization: Bearer SALES_EXEC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reply_text": "Your CRM looks interesting. Can you send pricing and explain WhatsApp integration?"}'
```

### 5. Generate Response
```bash
curl -X POST http://localhost:8000/api/v1/ai/leads/{lead_id}/generate-response \
  -H "Authorization: Bearer SALES_EXEC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reply_text": "Interested in pricing", "response_type": "draft"}'
```

### 6. Run Lead Miner
```bash
curl -X POST http://localhost:8000/api/v1/ai/lead-miner/run \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "icp_definition": {
      "name": "SaaS Companies",
      "description": "B2B SaaS companies with 50-500 employees",
      "industries": ["saas", "software", "technology"],
      "company_size_range": [50, 500],
      "geographies": ["US", "CA", "UK"],
      "technologies": ["react", "aws", "postgresql"],
      "keywords": ["b2b", "saas", "platform"],
      "exclude_industries": ["consumer", "retail"],
      "exclude_keywords": ["agency", "consulting"]
    },
    "max_prospects": 20,
    "min_score_threshold": 85
  }'
```

### 7. Generate Proposal
```bash
curl -X POST http://localhost:8000/api/v1/ai/deals/{deal_id}/generate-proposal \
  -H "Authorization: Bearer SALES_EXEC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 8. Chat with AI Assistant
```bash
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Authorization: Bearer SALES_EXEC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Find my best 20 leads today and create a campaign for them"}'
```

### 9. Check AI Usage Analytics
```bash
curl -X GET http://localhost:8000/api/v1/ai/usage/analytics?days=30 \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

## AI Assistant Available Tools (Permission-Gated)

| Tool | Required Permissions | Description |
|------|---------------------|-------------|
| `search_leads` | `ai:read_leads`, `leads:read` | Search leads with filters |
| `get_lead` | `ai:read_leads`, `leads:read` | Get detailed lead info |
| `create_campaign` | `ai:draft_email`, `campaigns:write` | Create email campaign |
| `assign_lead` | `ai:assign_leads`, `leads:assign` | Assign lead to salesperson |
| `schedule_followup` | `ai:draft_email`, `tasks:write` | Schedule follow-up task |
| `send_email` | `ai:send_email`, `campaigns:send` | Send email |
| `create_proposal` | `ai:create_proposal`, `deals:write` | Generate proposal |
| `update_stage` | `ai:change_stage`, `deals:write` | Update deal stage |
| `search_contacts` | `contacts:read` | Search contacts |
| `get_deal` | `deals:read` | Get deal details |
| `search_companies` | `companies:read` | Search companies |

## Architecture Highlights

### AI Router (Local-First, Cloud-Fallback)
```
User Request → AI Router → Local Capable? → Ollama (local)
                              ↓ No
                        Cloud Router → Cheapest Capable Model
                              ↓
                        Provider (NVIDIA/OpenAI/Anthropic)
                              ↓
                        Log to AIUsageLog (cost, tokens, latency)
```

### Controlled Tool Calling (AI Assistant)
```
User Message → System Prompt + Tools → AI Model
                              ↓
                    Tool Calls? → Execute with Permission Checks
                              ↓
                    Tool Results → AI Model → Final Response
```

### Lead Mining Pipeline
```
ICP Definition → AI Search → Company List
                    ↓
              Enrichment (AI) → Contact Info, Tech Stack, Signals
                    ↓
              ICP Scoring → Score ≥ 85?
                    ↓ Yes
              Create Lead + Contact + Company + Touchpoint + Activity
```

### Proposal Generation
```
Deal Context → Products + Pricing + Meeting Notes → AI Generator
                    ↓
              Executive Summary + Solution + Pricing + Terms + Next Steps
                    ↓
              Proposal Record (versioned, AI-tagged) + Activity
```

## Monitoring & Observability

### AI Usage Ledger (Every Invocation)
- Tenant, User, Task Type
- Provider, Model
- Input/Output Tokens, Total Tokens
- Estimated Cost (USD)
- Latency (ms)
- Success/Failure, Error Message
- Tool Actions Called
- Correlation ID
- Timestamp

### Analytics Dashboard (via API)
```bash
GET /api/v1/ai/usage/analytics?days=30
```
Returns:
- By task type: count, tokens, cost, avg latency
- By provider: count, tokens, cost
- Daily: count, tokens, cost

## Blueprint Alignment Checklist

| Blueprint Feature | Status |
|-------------------|--------|
| AI Router (local + cloud) | ✅ |
| Local Ollama for simple tasks | ✅ |
| NVIDIA NIM as primary cloud | ✅ |
| AI Usage Ledger (cost control) | ✅ |
| Level 3 AI Sales Agent | ✅ |
| Lead Scoring (explainable) | ✅ |
| Auto Assignment (hybrid) | ✅ |
| Next Best Action | ✅ |
| Reply Analysis (intent/sentiment) | ✅ |
| Auto Response Generation | ✅ |
| Lead Miner (ICP-based) | ✅ |
| Proposal Generator | ✅ |
| In-CRM AI Assistant (tools) | ✅ |
| Permission-Gated Tools | ✅ |
| AI Cost Tracking | ✅ |
| Multi-Model Routing | ✅ |

## Next Phases Ready

| Phase | Focus |
|-------|-------|
| **Phase 6** | Billing/Subscriptions (Stripe), Usage metering, Package admin |
| **Phase 7** | White-label, Custom domains, SSO, Advanced audit |
| **Phase 8** | Mobile app, Advanced reporting, Predictive analytics |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `NVIDIA_API_KEY not set` | Add to `.env` from https://build.nvidia.com/ |
| `Ollama connection refused` | Start Ollama: `ollama serve` and pull model: `ollama pull llama3.2:3b` |
| `Permission denied` | Check user role has required AI permissions, tenant has feature enabled |
| `AI timeout` | Increase timeout in config, check Ollama/cloud API status |
| `No leads created by miner` | Lower `min_score_threshold`, check ICP criteria breadth |
| `Proposal missing pricing` | Ensure deal has products/pricing in custom_fields |

---

**The AI Sales Agent is now operational!** 🎯

The system implements Level 3 controlled AI autonomy with:
- **Security**: Permission-gated tools, tenant isolation, encrypted credentials
- **Explainability**: Every AI decision has reasoning, factors, confidence
- **Cost Control**: Usage ledger, per-tenant limits, cheapest-model routing
- **Human-in-Loop**: Auto-respond requires approval, drafts by default
- **Observability**: Full audit trail, analytics, correlation IDs