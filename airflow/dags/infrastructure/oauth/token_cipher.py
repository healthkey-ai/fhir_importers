"""Symmetric encryption for OAuth tokens at rest in `fhir_connection`.

Uses Fernet (AES-128-CBC + HMAC-SHA256). The key lives in the
`FHIR_TOKEN_ENCRYPTION_KEY` env var; the same key must be configured for
Django (initial OAuth callback writes) and for Airflow workers (refresh
reads + writes).

Supports rotation: set `FHIR_TOKEN_ENCRYPTION_KEY` to a comma-separated
list — the *first* key is used for new encryption, all keys are tried for
decryption (`MultiFernet`). Migrate tokens forward by reading + writing
them back; the leading key is what re-encrypts.
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet, MultiFernet, InvalidToken


class TokenCipherError(Exception):
    """Raised when encryption/decryption fails (bad key, corrupted ciphertext)."""


class TokenCipher:
    """Encrypts and decrypts short strings (OAuth tokens) using Fernet."""

    _ENV_VAR = "FHIR_TOKEN_ENCRYPTION_KEY"

    def __init__(self, keys: list[bytes] | None = None):
        if keys is None:
            keys = self._load_keys_from_env()
        if not keys:
            raise TokenCipherError(
                f"No keys configured. Set {self._ENV_VAR} to a Fernet key "
                "(or comma-separated list for rotation)."
            )
        self._fernet = MultiFernet([Fernet(k) for k in keys])

    @classmethod
    def from_env(cls) -> "TokenCipher":
        return cls(keys=cls._load_keys_from_env())

    @staticmethod
    def _load_keys_from_env() -> list[bytes]:
        raw = os.environ.get(TokenCipher._ENV_VAR, "").strip()
        if not raw:
            return []
        return [k.strip().encode() for k in raw.split(",") if k.strip()]

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None:
            raise TokenCipherError("Cannot encrypt None")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            raise TokenCipherError("Cannot decrypt empty ciphertext")
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as e:
            raise TokenCipherError(
                "Decryption failed — token corrupted, encrypted under a different "
                "key, or current key list is missing the encrypting key."
            ) from e
