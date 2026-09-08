"""One authenticated encryption boundary for every persisted provider secret."""
import json
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


class CredentialService:
    prefix = "enc:v1:"

    def __init__(self, key=None):
        from app.core.config import get_settings
        key = key or get_settings().security.credential_encryption_key
        if not key:
            raise ValueError("SECURITY_CREDENTIAL_ENCRYPTION_KEY is required")
        self.cipher = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, value: str) -> str:
        return self.prefix + self.cipher.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        if not value.startswith(self.prefix):
            raise ValueError("Plaintext credentials are forbidden; run credential migration")
        try:
            return self.cipher.decrypt(value[len(self.prefix):].encode()).decode()
        except InvalidToken:
            raise ValueError("Credential decryption failed") from None


class EncryptedText(TypeDecorator):
    """All ORM routes and workers encrypt on bind and decrypt only in process memory."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return CredentialService().encrypt(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return CredentialService().decrypt(value) if value is not None else None


class EncryptedJSON(EncryptedText):
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return super().process_bind_param(json.dumps(value), dialect) if value is not None else None

    def process_result_value(self, value, dialect):
        return json.loads(super().process_result_value(value, dialect)) if value is not None else None
