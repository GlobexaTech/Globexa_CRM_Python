"""
Credential Encryption Service

Provides centralized AES-256-GCM encryption for integration credentials,
API keys, OAuth tokens, webhook secrets, and other sensitive data.
"""

import base64
import json
import os
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from app.core.config import get_settings


class CredentialEncryptionError(Exception):
    """Raised when encryption/decryption fails."""
    pass


class CredentialEncryption:
    """
    AES-256-GCM authenticated encryption for credentials.
    
    Uses a dedicated encryption key derived from SECURITY_CREDENTIAL_ENCRYPTION_KEY
    via HKDF. Each encryption operation uses a unique random nonce.
    
    The encrypted format is: nonce(12 bytes) + ciphertext + tag (16 bytes)
    All base64 encoded for storage.
    """
    
    _instance: Optional['CredentialEncryption'] = None
    _key: Optional[bytes] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._key is None:
            self._initialize_key()
    
    def _initialize_key(self) -> None:
        """Initialize encryption key from settings."""
        settings = get_settings()
        
        # Get the master encryption key from environment
        master_key = os.getenv("SECURITY_CREDENTIAL_ENCRYPTION_KEY")
        if not master_key:
            # In development, allow a default but warn
            if settings.app.environment == "development":
                master_key = "dev-master-key-change-in-production-32-chars-minimum"
            else:
                raise CredentialEncryptionError(
                    "SECURITY_CREDENTIAL_ENCRYPTION_KEY must be set in production"
                )
        
        # Derive a 32-byte key using HKDF
        # Use a fixed salt for deterministic derivation from master key
        # In production, consider rotating this with key versioning
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"globexa-credential-encryption-v1",
            info=b"credential-encryption",
        )
        self._key = hkdf.derive(master_key.encode())
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string using AES-256-GCM.
        
        Args:
            plaintext: The string to encrypt (typically JSON)
            
        Returns:
            Base64-encoded ciphertext with nonce and auth tag
            
        Raises:
            CredentialEncryptionError: If encryption fails
        """
        if not plaintext:
            raise CredentialEncryptionError("Cannot encrypt empty string")
        
        try:
            # Generate a random 12-byte nonce (recommended for GCM)
            nonce = os.urandom(12)
            
            # Create AESGCM cipher
            aesgcm = AESGCM(self._key)
            
            # Encrypt - returns ciphertext + auth tag combined
            ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
            
            # Combine nonce + ciphertext (which includes auth tag at the end)
            # Format: nonce (12) + ciphertext_with_tag
            encrypted_data = nonce + ciphertext
            
            # Base64 encode for storage
            return base64.b64encode(encrypted_data).decode()
            
        except Exception as e:
            raise CredentialEncryptionError(f"Encryption failed: {e}")
    
    def decrypt(self, encrypted_b64: str) -> str:
        """
        Decrypt a base64-encoded ciphertext.
        
        Args:
            encrypted_b64: Base64-encoded encrypted data (nonce + ciphertext + tag)
            
        Returns:
            Decrypted plaintext string
            
        Raises:
            CredentialEncryptionError: If decryption fails (tampering, wrong key, etc.)
        """
        if not encrypted_b64:
            raise CredentialEncryptionError("Cannot decrypt empty string")
        
        try:
            # Decode base64
            encrypted_data = base64.b64decode(encrypted_b64)
            
            # Extract nonce (first 12 bytes) and ciphertext+tag (rest)
            if len(encrypted_data) < 12 + 16:  # nonce + minimum ciphertext + tag
                raise CredentialEncryptionError("Invalid encrypted data: too short")
            
            nonce = encrypted_data[:12]
            ciphertext_with_tag = encrypted_data[12:]
            
            # Create AESGCM cipher
            aesgcm = AESGCM(self._key)
            
            # Decrypt and verify auth tag
            plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
            
            return plaintext.decode()
            
        except Exception as e:
            # Don't expose details about why decryption failed
            raise CredentialEncryptionError("Decryption failed: invalid data or key")
    
    def encrypt_json(self, data: Dict[str, Any]) -> str:
        """Encrypt a JSON-serializable dictionary."""
        json_str = json.dumps(data, separators=(',', ':'), sort_keys=True)
        return self.encrypt(json_str)
    
    def decrypt_json(self, encrypted_b64: str) -> Dict[str, Any]:
        """Decrypt to a JSON dictionary."""
        json_str = self.decrypt(encrypted_b64)
        return json.loads(json_str)


# Global instance
credential_encryption = CredentialEncryption()


def get_credential_encryption() -> CredentialEncryption:
    """Get the global credential encryption instance."""
    return credential_encryption


# Convenience functions
def encrypt_credentials(credentials: Dict[str, Any]) -> str:
    """Encrypt credentials dictionary for storage."""
    return credential_encryption.encrypt_json(credentials)


def decrypt_credentials(encrypted_b64: str) -> Dict[str, Any]:
    """Decrypt stored credentials."""
    return credential_encryption.decrypt_json(encrypted_b64)


def encrypt_string(value: str) -> str:
    """Encrypt a single string value."""
    return credential_encryption.encrypt(value)


def decrypt_string(encrypted_b64: str) -> str:
    """Decrypt a single string value."""
    return credential_encryption.decrypt(encrypted_b64)