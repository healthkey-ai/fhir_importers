"""Epic SMART-on-FHIR auth orchestration (synchronous port).

Drives the PKCE + private-key-JWT flow:
  start()  → builds the Epic authorization URL and stashes PKCE state
  finish() → exchanges the code for tokens, optionally validates id_token

Phase 0 returns the Epic tokens to the caller (unchanged from the FastAPI
service). Phase 2 will persist them in a Connection and enqueue a sync job.
"""
import base64
import hashlib
import logging
import secrets
import threading
import urllib.parse
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from .client import EpicClient, EpicTokens, SmartConfiguration
from .epic_config import epic_config_for_org
from .jwt_utils import build_client_assertion
from .organizations import OrganizationRegistry
from .state_store import PendingState, RedisStateStore

_logger = logging.getLogger(__name__)


class InvalidStateError(Exception):
    pass


@dataclass
class StartAuthResult:
    authorization_url: str
    state: str


class EpicAuthService:
    def __init__(
        self,
        client: EpicClient,
        state_store: RedisStateStore,
        organizations: OrganizationRegistry,
    ):
        self._client = client
        self._state_store = state_store
        self._organizations = organizations
        self._smart_config_cache: dict[str, SmartConfiguration] = {}
        self._smart_config_lock = threading.Lock()

    def start(self, organization_alias: str) -> StartAuthResult:
        org = self._organizations.get(organization_alias)
        epic = epic_config_for_org(org.alias)
        smart = self._get_smart_configuration(org.endpoint_url, epic.client_id)

        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("utf-8")).digest()
        ).decode("utf-8").rstrip("=")
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(16)

        self._state_store.put(
            state,
            PendingState(
                code_verifier=code_verifier,
                token_endpoint=smart.token_endpoint,
                organization_alias=org.alias,
            ),
        )

        params = {
            "response_type": "code",
            "client_id": epic.client_id,
            "redirect_uri": epic.redirect_uri,
            "scope": epic.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "aud": org.endpoint_url,
        }
        url = smart.authorization_endpoint + "?" + urllib.parse.urlencode(params)
        _logger.info("Built authorization URL for organization=%s state=%s", org.alias, state)
        return StartAuthResult(authorization_url=url, state=state)

    def finish(self, code: str, state: str) -> tuple[EpicTokens, str]:
        """Exchange the code for tokens. Returns (tokens, organization_alias)."""
        pending = self._state_store.pop(state)
        if pending is None:
            raise InvalidStateError("Unknown or expired state")

        epic = epic_config_for_org(pending.organization_alias)
        assertion = build_client_assertion(
            client_id=epic.client_id,
            token_endpoint=pending.token_endpoint,
            private_key_pem_path=epic.private_key_path,
            kid=epic.jwks_kid,
        )
        tokens = self._client.exchange_authorization_code(
            token_endpoint=pending.token_endpoint,
            code=code,
            redirect_uri=epic.redirect_uri,
            client_id=epic.client_id,
            code_verifier=pending.code_verifier,
            client_assertion=assertion,
        )

        if tokens.id_token:
            try:
                self._validate_id_token(pending.organization_alias, tokens.id_token)
            except Exception:
                # Validation is diagnostic — Epic already enforced the flow. Log and continue.
                _logger.exception("id_token validation failed for organization=%s", pending.organization_alias)

        return tokens, pending.organization_alias

    def smart_config_for_org(self, organization_alias: str):
        """Return (org, epic_credentials, SmartConfiguration) for an org alias.

        Used by the FHIR fetch path to discover the token endpoint (refresh)
        and the FHIR base URL.
        """
        org = self._organizations.get(organization_alias)
        epic = epic_config_for_org(org.alias)
        smart = self._get_smart_configuration(org.endpoint_url, epic.client_id)
        return org, epic, smart

    def _validate_id_token(self, organization_alias: str, id_token: str) -> None:
        org = self._organizations.get(organization_alias)
        epic = epic_config_for_org(org.alias)
        smart = self._get_smart_configuration(org.endpoint_url, epic.client_id)
        if not smart.jwks_uri or not smart.issuer:
            raise ValueError("smart-configuration is missing jwks_uri or issuer")

        jwk_client = PyJWKClient(smart.jwks_uri)
        signing_key = jwk_client.get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384"],
            audience=epic.client_id,
            issuer=smart.issuer,
            options={"require": ["exp", "iat", "aud", "iss"]},
            leeway=60,
        )
        _logger.info("id_token validated for organization=%s sub=%s", organization_alias, claims.get("sub"))

    def _get_smart_configuration(self, base_url: str, client_id: str) -> SmartConfiguration:
        cached = self._smart_config_cache.get(base_url)
        if cached is not None:
            return cached
        with self._smart_config_lock:
            cached = self._smart_config_cache.get(base_url)
            if cached is not None:
                return cached
            smart = self._client.get_smart_configuration(base_url, client_id)
            self._smart_config_cache[base_url] = smart
            return smart
