"""HTTP client for ctomop's POST /api/fhir/sync/ (mirrors hk-labs' ctomop_client).

Identity travels in the body (actor_iss/actor_sub); transport is authenticated
with CTOMOP_SERVICE_TOKEN (an OAuth2 patient/*.write bearer). A forwarded user
token may be passed instead when available.
"""
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

def _timeout() -> httpx.Timeout:
    # ctomop ingests the whole patient compartment synchronously in the request
    # (per-row concept lookups + PatientInfo refresh), so a first full-patient
    # sync can take a while. Read timeout is generous + configurable.
    read = getattr(settings, "CTOMOP_HTTP_TIMEOUT_SECONDS", 180.0)
    return httpx.Timeout(connect=5.0, read=read, write=30.0, pool=5.0)


class CtomopSyncError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass
class FhirSyncResult:
    person_id: int | None
    measurement_ids: list
    condition_ids: list
    drug_exposure_ids: list

    @property
    def created_count(self) -> int:
        return len(self.measurement_ids) + len(self.condition_ids) + len(self.drug_exposure_ids)


def is_enabled() -> bool:
    return bool(getattr(settings, "CTOMOP_SYNC_URL", ""))


def _headers(bearer_token: str = "") -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    token = bearer_token or getattr(settings, "CTOMOP_SERVICE_TOKEN", "")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def sync_fhir_bundle(
    *,
    bundle: dict,
    actor_iss: str = "",
    actor_sub: str = "",
    person_id: int | None = None,
    bearer_token: str = "",
) -> FhirSyncResult:
    """POST a FHIR Bundle to ctomop. Raises CtomopSyncError on failure."""
    url = getattr(settings, "CTOMOP_SYNC_URL", "")
    if not url:
        raise CtomopSyncError("CTOMOP_SYNC_URL not configured")

    payload: dict = {"bundle": bundle}
    if actor_iss and actor_sub:
        payload["actor_iss"] = actor_iss
        payload["actor_sub"] = actor_sub
    if person_id is not None:
        payload["person_id"] = person_id

    try:
        with httpx.Client(timeout=_timeout()) as client:
            resp = client.post(url, json=payload, headers=_headers(bearer_token))
    except httpx.HTTPError as exc:
        raise CtomopSyncError(f"ctomop sync request failed: {exc}") from exc

    if resp.status_code >= 400:
        logger.error("ctomop fhir sync failed: %s %s", resp.status_code, resp.text[:500])
        raise CtomopSyncError(
            f"ctomop sync returned {resp.status_code}",
            status_code=resp.status_code,
            body=resp.text,
        )

    data = resp.json()
    return FhirSyncResult(
        person_id=data.get("person_id"),
        measurement_ids=data.get("measurement_ids", []),
        condition_ids=data.get("condition_ids", []),
        drug_exposure_ids=data.get("drug_exposure_ids", []),
    )
