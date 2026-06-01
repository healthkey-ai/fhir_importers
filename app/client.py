import abc
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


class BaseEpicClient(abc.ABC):
    """Outbound HTTP to an Epic FHIR server: SMART discovery + token exchange."""

    @abc.abstractmethod
    async def get_smart_configuration(
        self, base_url: str, client_id: str
    ) -> SmartConfiguration: ...

    @abc.abstractmethod
    async def exchange_authorization_code(
        self,
        token_endpoint: str,
        code: str,
        redirect_uri: str,
        client_id: str,
        code_verifier: str,
        client_assertion: str,
    ) -> EpicTokens: ...


class EpicClient(BaseEpicClient):
    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def get_smart_configuration(self, base_url: str, client_id: str) -> SmartConfiguration:
        url = base_url.rstrip("/") + "/.well-known/smart-configuration"
        headers = {"Accept": "application/json", "Epic-Client-ID": client_id}
        response = await self._http.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return SmartConfiguration(
            authorization_endpoint=data["authorization_endpoint"],
            token_endpoint=data["token_endpoint"],
            issuer=data.get("issuer"),
            jwks_uri=data.get("jwks_uri"),
        )

    async def exchange_authorization_code(
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
        response = await self._http.post(token_endpoint, data=body, headers=headers)
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
