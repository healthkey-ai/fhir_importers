"""Symmetric encryption for Epic tokens at rest.

Epic access/refresh tokens are PHI-adjacent secrets — they must never be stored
in plaintext. We encrypt with Fernet (AES-128-CBC + HMAC).

Key resolution:
  - settings.TOKEN_ENCRYPTION_KEY (a urlsafe-base64 32-byte Fernet key) in prod.
  - Dev fallback: derive a stable key from SECRET_KEY so local dev works with no
    extra config. NEVER rely on the fallback in production — set the real key.
"""
import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet
from django.conf import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = getattr(settings, "TOKEN_ENCRYPTION_KEY", "") or ""
    if not key:
        # Deterministic dev key derived from SECRET_KEY (32 bytes → urlsafe b64).
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    return _fernet().decrypt(token.encode()).decode()
