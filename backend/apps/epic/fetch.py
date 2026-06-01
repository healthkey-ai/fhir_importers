"""Build a FHIR Bundle for a Connection by fetching from Epic.

Ensures a non-expired access token (refreshing + persisting if needed), then
pulls the patient compartment via Patient/$everything.
"""
import logging
from datetime import timedelta

import httpx
from django.conf import settings
from django.utils import timezone

from .client import EpicClient
from .fhir_client import EpicFhirClient
from .jwt_utils import build_client_assertion
from .services import get_auth_service

logger = logging.getLogger(__name__)

_REFRESH_SKEW = timedelta(seconds=60)


def _ensure_fresh_token(connection) -> str:
    """Return a usable access token, refreshing + persisting if it's near expiry."""
    exp = connection.token_expires_at
    if exp and exp > timezone.now() + _REFRESH_SKEW:
        return connection.access_token
    if not connection.refresh_token:
        # No refresh token (no offline_access) — use what we have; a 401 from
        # Epic will surface as a failed SyncJob.
        return connection.access_token

    _, epic, smart = get_auth_service().smart_config_for_org(connection.org_alias)
    assertion = build_client_assertion(
        client_id=epic.client_id,
        token_endpoint=smart.token_endpoint,
        private_key_pem_path=epic.private_key_path,
        kid=epic.jwks_kid,
    )
    with httpx.Client(timeout=settings.EPIC_HTTP_TIMEOUT_SECONDS) as http:
        tokens = EpicClient(http).refresh_access_token(
            token_endpoint=smart.token_endpoint,
            refresh_token=connection.refresh_token,
            client_id=epic.client_id,
            client_assertion=assertion,
        )

    connection.access_token = tokens.access_token
    if tokens.refresh_token:
        connection.refresh_token = tokens.refresh_token
    if tokens.scope:
        connection.scope = tokens.scope
    connection.token_expires_at = timezone.now() + timedelta(seconds=tokens.expires_in)
    connection.save(update_fields=[
        "access_token_enc", "refresh_token_enc", "scope", "token_expires_at", "updated_at",
    ])
    logger.info("Refreshed Epic access token for connection %s", connection.id)
    return tokens.access_token


def build_bundle_for_connection(connection) -> dict:
    """Fetch the patient compartment from Epic for *connection* as a Bundle."""
    access_token = _ensure_fresh_token(connection)
    org, _, _ = get_auth_service().smart_config_for_org(connection.org_alias)
    with httpx.Client(timeout=settings.EPIC_HTTP_TIMEOUT_SECONDS) as http:
        return EpicFhirClient(http, access_token).fetch_patient_everything(
            org.endpoint_url, connection.epic_patient_id,
        )
