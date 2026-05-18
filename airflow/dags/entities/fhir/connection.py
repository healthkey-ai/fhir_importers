from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum


class FhirConnectionStatus(StrEnum):
    """Mirrors `fhir_connection.status` choices on the Django side."""

    CONNECTED = "connected"
    EXPIRING_SOON = "expiring_soon"
    NEEDS_REAUTH = "needs_reauth"
    REVOKED = "revoked"
    DEGRADED = "degraded"


@dataclass
class SmartTokens:
    """Plaintext OAuth tokens. Lives in memory only — never persisted."""

    access_token: str
    refresh_token: str
    expires_at: datetime


@dataclass
class FhirConnection:
    """Mirrors the Django `fhir_connection` table.

    Token fields hold ciphertext when round-tripped from the DB; the
    `SmartTokenRefresher` decrypts/encrypts via `TokenCipher`. Plaintext
    tokens never travel as part of this dataclass — they live in a
    `SmartTokens` instance held in-memory inside the refresher.
    """

    id: int | None = None
    person_id: int | None = None
    institution_id: int | None = None
    organization_id: int | None = None

    # Fernet ciphertext. Plaintext access via TokenCipher only.
    access_token_encrypted: str = ""
    refresh_token_encrypted: str = ""

    expires_at: datetime | None = None
    scope_granted: str = ""

    fhir_patient_id: str | None = None

    status: FhirConnectionStatus = FhirConnectionStatus.CONNECTED

    last_successful_sync: datetime | None = None
    last_attempted_sync: datetime | None = None
    last_token_refresh_at: datetime | None = None
    failure_count: int = 0
    last_error: str = ""

    created_at: datetime | None = None
    updated_at: datetime | None = None

    def is_expired(self, skew_seconds: int = 30) -> bool:
        """True if the access_token is within `skew_seconds` of (or past) expiry."""
        if self.expires_at is None:
            return True
        now = datetime.now(tz=timezone.utc)
        # Tolerate naive datetimes from the DB driver
        deadline = self.expires_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return deadline - timedelta(seconds=skew_seconds) <= now
