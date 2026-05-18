from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Institution:
    """Mirrors the Django `fhir_institution` table.

    Holds per-vendor SMART config + the retry/backoff parameters that encode
    HealthTree's observed institutional behaviour (Architecture Recommendations
    v1.1 § 2.1.1 and § 2.3.4).
    """

    id: int | None = None
    slug: str = ""
    display_name: str = ""

    # SMART/FHIR endpoints
    fhir_base: str = ""
    smart_config_url: str = ""
    client_id: str = ""
    scopes: str = ""
    redirect_uri: str = ""

    # Asymmetric client auth — None disables JWT client auth (PKCE-only).
    jwks_kid: str | None = None

    # Capabilities
    supports_bulk_export: bool = False

    # Retry / backoff
    base_backoff_seconds: int = 1
    max_backoff_seconds: int = 300
    max_retry_count: int = 5
    respect_retry_after: bool = True
    jitter_factor: float = 0.1
    retryable_status_codes: list[int] = field(default_factory=list)
    daily_quota_reset_utc_hour: int | None = None

    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
