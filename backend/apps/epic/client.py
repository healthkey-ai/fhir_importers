"""Synchronous HTTP layer to Epic (ported from the async FastAPI client)."""
import logging
from dataclasses import dataclass

import httpx

_logger = logging.getLogger(__name__)


@dataclass
class SmartConfiguration:
    authorization_endpoint: str
    token_endpoint: str
    issuer: str | None
    jwks_uri: str | None


@dataclass
class EpicTokens:
    access_token: str
    refresh_token: str | None
    id_token: str | None
    expires_in: int
    scope: str | None
    patient: str | None


class EpicClient:
    def __init__(self, http: httpx.Client):
        self._http = http

    def get_smart_configuration(self, base_url: str, client_id: str) -> SmartConfiguration:
        url = base_url.rstrip("/") + "/.well-known/smart-configuration"
        headers = {"Accept": "application/json", "Epic-Client-ID": client_id}
        response = self._http.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return SmartConfiguration(
            authorization_endpoint=data["authorization_endpoint"],
            token_endpoint=data["token_endpoint"],
            issuer=data.get("issuer"),
            jwks_uri=data.get("jwks_uri"),
        )

    def exchange_authorization_code(
        self,
        token_endpoint: str,
        code: str,
        redirect_uri: str,
        client_id: str,
        code_verifier: str,
        client_assertion: str,
    ) -> EpicTokens:
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": client_assertion,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        response = self._http.post(token_endpoint, data=body, headers=headers)
        if response.status_code >= 400:
            _logger.error("Epic token exchange failed: %s %s", response.status_code, response.text)
        response.raise_for_status()
        data = response.json()
        return EpicTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            id_token=data.get("id_token"),
            expires_in=data["expires_in"],
            scope=data.get("scope"),
            patient=data.get("patient"),
        )

    def refresh_access_token(
        self,
        token_endpoint: str,
        refresh_token: str,
        client_id: str,
        client_assertion: str,
    ) -> EpicTokens:
        """Exchange a refresh_token for a fresh access token (offline_access)."""
        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": client_assertion,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        response = self._http.post(token_endpoint, data=body, headers=headers)
        if response.status_code >= 400:
            _logger.error("Epic token refresh failed: %s %s", response.status_code, response.text)
        response.raise_for_status()
        data = response.json()
        return EpicTokens(
            access_token=data["access_token"],
            # Epic may or may not rotate the refresh token; keep the old one if absent.
            refresh_token=data.get("refresh_token"),
            id_token=data.get("id_token"),
            expires_in=data["expires_in"],
            scope=data.get("scope"),
            patient=data.get("patient"),
        )
