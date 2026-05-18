"""SMART on FHIR access-token refresher.

Bridges `fhir_connection` rows (encrypted tokens) and live HTTP calls.
Given a connection_id:

  1. SELECT … FOR UPDATE the row (serialises concurrent refreshers across
     Django + Airflow workers — Section 3 of the plan).
  2. Decrypt access_token.
  3. If still valid → return plaintext (no network call).
  4. Otherwise: POST to the institution's token endpoint with
     grant_type=refresh_token, parse new tokens, encrypt, UPDATE row,
     return plaintext.
  5. If refresh fails with invalid_grant → mark connection NEEDS_REAUTH
     and raise `NeedsReauth` so callers can surface a re-auth prompt.

Network errors and 5xx are NOT special-cased here — let the surrounding
retry/backoff layer handle them.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from entities.fhir.connection import (
    FhirConnection,
    FhirConnectionStatus,
    SmartTokens,
)
from entities.fhir.institution import Institution
from infrastructure.oauth.client_assertion import build_client_assertion
from infrastructure.oauth.token_cipher import TokenCipher
from infrastructure.repository.fhir_connection import FhirConnectionRepository
from infrastructure.repository.institution import InstitutionRepository

_logger = logging.getLogger(__name__)


class SmartRefreshError(Exception):
    """Generic refresh failure (network, malformed response, etc.)."""


class NeedsReauth(SmartRefreshError):
    """Vendor said `invalid_grant` — the patient must re-consent.

    Connection row is flipped to `needs_reauth` before raising.
    """


class SmartTokenRefresher:
    """Returns a guaranteed-fresh access_token for a `fhir_connection`."""

    def __init__(
        self,
        connection_repository: FhirConnectionRepository,
        institution_repository: InstitutionRepository,
        token_cipher: TokenCipher,
    ):
        self._connections = connection_repository
        self._institutions = institution_repository
        self._cipher = token_cipher

    def fresh_tokens_for(self, connection_id: int) -> tuple[FhirConnection, SmartTokens]:
        """Acquire a row lock, refresh if needed, return (connection, plaintext tokens).

        The repository call MUST run inside a transaction the caller doesn't
        close before they're done with the tokens — the lock holds for the
        duration of that transaction. Practical pattern: spin a session,
        call this, do the FHIR pulls, commit/close.
        """
        with self._connections.lock_for_update(connection_id) as locked:
            tokens = SmartTokens(
                access_token=self._cipher.decrypt(locked.access_token_encrypted),
                refresh_token=self._cipher.decrypt(locked.refresh_token_encrypted),
                expires_at=locked.expires_at,
            )
            if not locked.is_expired():
                return locked, tokens

            institution = self._institutions.get_by_id(locked.institution_id)
            if institution is None:
                raise SmartRefreshError(
                    f"Connection {connection_id} references missing institution_id={locked.institution_id}"
                )

            refreshed = self._refresh_via_token_endpoint(institution, tokens.refresh_token)

            # Persist new tokens.
            locked.access_token_encrypted = self._cipher.encrypt(refreshed.access_token)
            locked.refresh_token_encrypted = self._cipher.encrypt(refreshed.refresh_token)
            locked.expires_at = refreshed.expires_at
            locked.last_token_refresh_at = datetime.now(tz=timezone.utc)
            locked.status = FhirConnectionStatus.CONNECTED
            locked.last_error = ""
            self._connections.update_tokens(locked)
            return locked, refreshed

    def _refresh_via_token_endpoint(
        self,
        institution: Institution,
        refresh_token: str,
    ) -> SmartTokens:
        token_endpoint = self._discover_token_endpoint(institution)
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": institution.client_id,
        }
        if institution.jwks_kid:
            data["client_assertion_type"] = (
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
            )
            data["client_assertion"] = build_client_assertion(
                client_id=institution.client_id,
                token_endpoint=token_endpoint,
                private_key_pem=self._load_private_key_pem(),
                kid=institution.jwks_kid,
            )

        _logger.info(
            "Refreshing token via %s for institution=%s", token_endpoint, institution.slug
        )
        response = requests.post(token_endpoint, data=data, timeout=15)

        if response.status_code == 400:
            # `invalid_grant` = refresh_token revoked/expired — needs re-auth.
            body = self._safe_json(response)
            if body.get("error") == "invalid_grant":
                self._connections.mark_needs_reauth(institution.id, reason=str(body))
                raise NeedsReauth(
                    f"institution={institution.slug}: refresh_token rejected ({body.get('error_description')})"
                )

        if not response.ok:
            raise SmartRefreshError(
                f"Token endpoint {token_endpoint} returned {response.status_code}: {response.text[:500]}"
            )

        body = response.json()
        access = body.get("access_token")
        refresh = body.get("refresh_token", refresh_token)  # some EHRs don't rotate
        expires_in = int(body.get("expires_in", 3600))
        if not access:
            raise SmartRefreshError(
                f"Token endpoint response missing access_token: {body}"
            )
        return SmartTokens(
            access_token=access,
            refresh_token=refresh,
            expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in),
        )

    @staticmethod
    def _discover_token_endpoint(institution: Institution) -> str:
        """Fetch .well-known/smart-configuration to find the token endpoint.

        Cached at the institution level — the configuration changes rarely.
        For now we re-fetch on every refresh; if this becomes a hot path,
        memoise on `institution.id` in process.
        """
        response = requests.get(institution.smart_config_url, timeout=10)
        response.raise_for_status()
        config = response.json()
        token_endpoint = config.get("token_endpoint")
        if not token_endpoint:
            raise SmartRefreshError(
                f"{institution.smart_config_url} returned no `token_endpoint`"
            )
        return token_endpoint

    @staticmethod
    def _load_private_key_pem() -> str:
        path = os.environ.get("FHIR_CLIENT_PRIVATE_KEY_PATH")
        if not path:
            raise SmartRefreshError(
                "FHIR_CLIENT_PRIVATE_KEY_PATH env var not set — "
                "asymmetric client auth requires a private key on disk."
            )
        with open(path, "r") as f:
            return f.read()

    @staticmethod
    def _safe_json(response: requests.Response) -> dict[str, Any]:
        try:
            return response.json()
        except ValueError:
            return {}
