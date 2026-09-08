"""Failed authentication survives the request rollback without storing identity secrets."""
import hashlib
from sqlalchemy import text
from app.core.database import AsyncSessionLocal


async def failed_authentication(email: str):
    # A nonreversible keyed identity fingerprint supports aggregation without raw emails.
    import hmac
    from app.core.config import get_settings
    digest = hmac.new(get_settings().security.secret_key.encode(), email.lower().encode(), hashlib.sha256).hexdigest()
    async with AsyncSessionLocal() as db:
        await db.execute(text("INSERT INTO security_events (action, principal_digest, success) VALUES ('auth.failed', :digest, false)"), {"digest": digest})
        await db.commit()
