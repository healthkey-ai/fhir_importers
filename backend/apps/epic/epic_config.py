"""Epic per-organization credential resolution, backed by Django settings.

Replaces the FastAPI pydantic `Settings` object. The sandbox org
(EPIC_STAGING_ORG_ALIAS) uses Epic's non-production credentials; every other
organization uses the production credentials.
"""
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


def resolve_private_key_pem(inline: str, path: str) -> str:
    """PEM text for an Epic signing key.

    Prefers the inline value (Secret Manager / env, as Cloud Run injects it);
    otherwise reads the file at `path` (local dev). Returns "" when neither is
    configured; raises OSError if a configured path can't be read.
    """
    if inline and inline.strip():
        return inline
    if path:
        return Path(path).read_text()
    return ""


@dataclass(frozen=True)
class EpicCredentials:
    client_id: str
    redirect_uri: str
    private_key_pem: str
    jwks_kid: str
    scopes: str


def _staging() -> EpicCredentials:
    return EpicCredentials(
        client_id=settings.EPIC_STAGING_CLIENT_ID,
        redirect_uri=settings.EPIC_STAGING_REDIRECT_URI,
        private_key_pem=resolve_private_key_pem(
            settings.EPIC_STAGING_PRIVATE_KEY, settings.EPIC_STAGING_PRIVATE_KEY_PATH
        ),
        jwks_kid=settings.EPIC_STAGING_JWKS_KID,
        scopes=settings.EPIC_STAGING_SCOPES,
    )


def _prod() -> EpicCredentials:
    return EpicCredentials(
        client_id=settings.EPIC_PROD_CLIENT_ID,
        redirect_uri=settings.EPIC_PROD_REDIRECT_URI,
        private_key_pem=resolve_private_key_pem(
            settings.EPIC_PROD_PRIVATE_KEY, settings.EPIC_PROD_PRIVATE_KEY_PATH
        ),
        jwks_kid=settings.EPIC_PROD_JWKS_KID,
        scopes=settings.EPIC_PROD_SCOPES,
    )


def epic_config_for_org(organization_alias: str) -> EpicCredentials:
    if organization_alias == settings.EPIC_STAGING_ORG_ALIAS:
        return _staging()
    return _prod()
