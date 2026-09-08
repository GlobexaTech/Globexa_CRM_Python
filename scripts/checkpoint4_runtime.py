"""Launch an isolated integration runtime; only external paid providers are substituted.

No HTTP test backdoors, authentication overrides, database fakes or eager Celery
tasks are installed. API, worker and scheduler use the restricted PostgreSQL role.
This entrypoint is excluded from the production Docker image.
"""
import argparse
import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import urlencode, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_environment():
    if os.environ.get("APP_ENVIRONMENT") != "testing":
        raise RuntimeError("The E2E runtime requires explicit APP_ENVIRONMENT=testing")
    settings_file = ROOT / "evidence" / "runtime.env.json"
    values = json.loads(settings_file.read_text(encoding="utf-8"))
    if values.get("APP_ENVIRONMENT") != "testing" or not values.get("DATABASE_NAME", "").startswith("globexa_cp4"):
        raise RuntimeError("Refusing to launch E2E adapters outside an isolated CP4 database")
    os.environ.update(values)
    os.chdir(ROOT)


def install_external_adapters():
    if os.environ.get("APP_ENVIRONMENT") != "testing" or not os.environ.get("DATABASE_NAME", "").startswith("globexa_cp4"):
        raise RuntimeError("External adapter fixtures are restricted to the isolated E2E runtime")
    from app.services.crm.providers import MailAdapter, ProviderFailure, adapters
    from app.services.ai.gateway import AIGateway, Generation, ModelRoute
    import app.services.crm.ai as ai

    class FixtureMail(MailAdapter):
        """Deterministic substitute at the external provider interface only."""

        def configuration(self):
            return {"client_id": "cp4-test-adapter", "client_secret": os.environ["CRM_GMAIL_CLIENT_SECRET"], "redirect_uri": os.environ["CRM_GMAIL_REDIRECT_URI"]}

        def authorization_url(self, state, challenge):
            # Real backend state/PKCE handling is retained. Tests inspect or finish
            # this local callback; no request reaches Google or Microsoft.
            return self.configuration()["redirect_uri"] + "?" + urlencode({"state": state, "code": "cp4-approved-provider-code"})

        async def connect(self, code, verifier, redirect_uri):
            if code != "cp4-approved-provider-code" or not verifier or redirect_uri != self.configuration()["redirect_uri"]:
                raise ProviderFailure("invalid_provider_code")
            return {"access_token": secrets.token_urlsafe(32), "refresh_token": secrets.token_urlsafe(32), "expires_in": 3600}

        async def refresh(self, token):
            if not token:
                raise ProviderFailure("invalid_refresh_token")
            return {"access_token": secrets.token_urlsafe(32), "expires_in": 3600}

        async def health_check(self, token):
            if not token:
                raise ProviderFailure("invalid_access_token")
            return {"connected": True, "address": "sender@example.com"}

        async def disconnect(self, token):
            return {"remote_revocation": True}

        async def send(self, token, message, idempotency_key):
            if "[provider-unknown]" in message.get("subject", ""):
                raise ProviderFailure("provider_timeout", uncertain=True)
            if "[provider-failure]" in message.get("subject", ""):
                raise ProviderFailure("provider_rejected")
            return {"provider_message_id": "fixture-" + sha256(idempotency_key.encode()).hexdigest()[:24], "status": "sent"}

        async def sync(self, token, cursor=None):
            return {"messages": [], "cursor": None}

    class FixtureModel:
        def __init__(self):
            import httpx
            # Conform to the configured external-provider lifecycle: the real
            # gateway closes this client after execution. generate sends no HTTP.
            self.client = httpx.AsyncClient(timeout=1, follow_redirects=False)

        async def generate(self, model, prompt):
            if "[ai-provider-failure]" in prompt:
                raise RuntimeError("fixture_external_provider_unavailable")
            capability = prompt.split("Produce a CRM ", 1)[1].split(" using", 1)[0]
            outputs = {
                "lead_score": {"score": 78, "confidence": 0.8, "reasons": ["Customer requested a discovery meeting"]},
                "lead_summary": {"summary": "Customer requested a discovery meeting. Confirm scope during follow-up."},
                "next_best_action": {"action": "Schedule discovery", "confidence": 0.8, "reasons": ["An open opportunity needs qualification"]},
                "reply_analysis": {"classification": "meeting_request", "confidence": 0.9, "summary": "Customer asks for a meeting."},
                "campaign_draft": {"subject": "Discovery follow-up", "body": "Please review this draft before sending."},
                "proposal_draft": {"subject": "Discovery proposal", "body": "Draft scope for human review using supplied facts."},
            }
            return Generation(json.dumps(outputs[capability]), 40, 20)

    for name in ("gmail", "outlook"):
        adapters[name] = FixtureMail(name)
    ai.build_gateway = lambda: AIGateway({"nvidia": FixtureModel()}, [ModelRoute("nvidia", "cp4-external-model-fixture")])


async def verify_runtime():
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core.config import get_settings
    from app.core.runtime_security import verify_runtime_security
    engine = create_async_engine(get_settings().database.url)
    async with engine.connect() as db:
        await verify_runtime_security(db)
    await engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["api", "worker", "scheduler", "frontend"])
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()
    load_environment()
    if args.kind == "frontend":
        # This invokes a fixed local CLI without a shell or user command input.
        import subprocess  # nosec B404
        origin = urlparse(os.environ["APP_ORIGIN"])
        command = ["node", "node_modules/next/dist/bin/next", "dev" if args.dev else "start", "--hostname", "127.0.0.1", "--port", str(origin.port or 3254)]
        # The only variable argument is a parsed integer port; shell is disabled.
        result = subprocess.run(command, cwd=ROOT / "frontend", check=False)  # nosec B603
        raise SystemExit(result.returncode)
    install_external_adapters()
    asyncio.run(verify_runtime())
    if args.kind == "api":
        import uvicorn
        from app.main import app
        port = urlparse(os.environ["BACKEND_API_URL"]).port or 8004
        uvicorn.run(app, host="127.0.0.1", port=port, access_log=False)
    elif args.kind == "worker":
        from app.workers.celery_app import celery_app
        celery_app.worker_main(["worker", "--pool=solo", "--concurrency=1", "--loglevel=WARNING", "--without-gossip", "--without-mingle", "--queues=celery,emails,campaigns,ai,integrations,usage"])
    else:
        from app.workers.tasks.foundation_tasks import dispatch_scheduled
        while True:
            dispatch_scheduled.delay()
            time.sleep(2)


if __name__ == "__main__":
    main()
