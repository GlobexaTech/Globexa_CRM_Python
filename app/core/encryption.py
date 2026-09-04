"""Encryption service for sensitive data (API keys, tokens, secrets).

Uses AES-GCM for authenticated encryption with a master key from environment.
"""
import os
import json
import base64
from typing import Optional, Dict, Any
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.exceptions import InvalidTag

from app.core.config import get_settings


class EncryptionService:
    """Centralized encryption/decryption service for sensitive data.
    
    Uses AES-GCM with a master key derived from the application secret key.
    The master key is never stored - it's derived from the application secret.
    """
    
    def __init__(self):
        self._master_key: Optional[bytes] = None
        self._aesgcm: Optional[AESGCM] = None
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize the encryption service with master key from settings."""
        settings = get_settings()
        master_key_base = settings.security.secret_key.encode()
        
        # Derive a 256-bit key using HKDF
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'globexa-crm-encryption-salt-v1',
            info=b'credential-encryption',
        )
        self._master_key = hkdf.derive(master_key_base)
        self._aesgcm = AESGCM(self._master_key)
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string and return base64-encoded ciphertext with nonce.
        
        Returns: base64(nonce + ciphertext + tag)
        """
        if not self._aesgcm:
            raise RuntimeError("Encryption service not initialized")
        
        if not plaintext:
            return ""
        
        # Generate a random 12-byte nonce for AES-GCM
        nonce = os.urandom(12)
        
        # Encrypt
        plaintext_bytes = plaintext.encode('utf-8')
        ciphertext = self._aesgcm.encrypt(nonce, plaintext_bytes, None)
        
        # Combine nonce + ciphertext and base64 encode
        encrypted = nonce + ciphertext
        return base64.b64encode(encrypted).decode('utf-8')
    
    def decrypt(self, ciphertext_b64: str) -> str:
        """Decrypt a base64-encoded ciphertext and return plaintext.
        
        Args:
            ciphertext_b64: base64(nonce + ciphertext + tag)
            
        Returns:
            Decrypted plaintext string
            
        Raises:
            InvalidToken: If decryption fails (wrong key, tampered data, etc.)
        """
        if not self._aesgcm:
            raise RuntimeError("Encryption service not initialized")
        
        if not ciphertext_b64:
            return ""
        
        try:
            # Decode base64
            encrypted = base64.b64decode(ciphertext_b64)
            
            # Extract nonce (first 12 bytes) and ciphertext
            nonce = encrypted[:12]
            ciphertext = encrypted[12:]
            
            # Decrypt
            plaintext_bytes = self._aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext_bytes.decode('utf-8')
        except InvalidTag:
            raise ValueError("Decryption failed: invalid key or tampered data")
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")
    
    def encrypt_dict(self, data: Dict[str, Any]) -> str:
        """Encrypt a dictionary as JSON."""
        if not data:
            return ""
        json_str = json.dumps(data, separators=(',', ':'))
        return self.encrypt(json_str)
    
    def decrypt_dict(self, ciphertext_b64: str) -> Dict[str, Any]:
        """Decrypt to a dictionary."""
        if not ciphertext_b64:
            return {}
        json_str = self.decrypt(ciphertext_b64)
        return json.loads(json_str)
    
    def rotate_key(self, new_master_key: str) -> None:
        """Rotate the master key (for key rotation).
        
        This re-encrypts all stored data with the new key.
        Should be called with a migration strategy.
        """
        # This would require decrypting all existing data with old key
        # and re-encrypting with new key. Implement as needed.
        pass


# Singleton instance
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """Get the singleton encryption service instance."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def encrypt_credentials(credentials: Dict[str, Any]) -> str:
    """Convenience function to encrypt credentials dict."""
    return get_encryption_service().encrypt_dict(data=credentials)


def decrypt_credentials(encrypted: str) -> Dict[str, Any]:
    """Convenience function to decrypt credentials to dict."""
    if not encrypted:
        return {}
    return get_encryption_service().decrypt_dict(ciphertext_b64=encrypted)


# Convenience functions for specific credential types
def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key."""
    return get_encryption_service().encrypt(api_key)


def decrypt_api_key(encrypted: str) -> str:
    """Decrypt an API key."""
    return get_encryption_service().decrypt(encrypted)


def encrypt_oauth_tokens(access_token: str, refresh_token: Optional[str] = None) -> str:
    """Encrypt OAuth tokens."""
    data = {"access_token": access_token}
    if refresh_token:
        data["refresh_token"] = refresh_token
    return get_encryption_service().encrypt_dict(data)


def decrypt_oauth_tokens(encrypted: str) -> Dict[str, str]:
    """Decrypt OAuth tokens."""
    return get_encryption_service().decrypt_dict(encrypted)


def encrypt_webhook_secret(secret: str) -> str:
    """Encrypt a webhook secret."""
    return get_encryption_service().encrypt(secret)


def decrypt_webhook_secret(encrypted: str) -> str:
    """Decrypt a webhook secret."""
    return get_encryption_service().decrypt(encrypted)