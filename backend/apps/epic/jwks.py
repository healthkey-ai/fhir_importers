"""Serve the connector's public signing keys as a JWKS.

Epic (and any SMART server) fetches this to verify the private-key-JWT
client_assertion the connector sends at the token endpoint. Registering Epic's
**Production JWK Set URL** at this endpoint makes key rotation a deploy rather
than a re-registration.

Only PUBLIC key material is exposed — derived from the configured private keys,
never the private keys themselves.
"""
import json
import logging
from functools import lru_cache

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from django.conf import settings
from jwt.algorithms import RSAAlgorithm
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .epic_config import resolve_private_key_pem

logger = logging.getLogger(__name__)


def _public_jwk(private_key_pem: str, kid: str) -> dict:
    key = load_pem_private_key(private_key_pem.encode(), password=None)
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return jwk


@lru_cache(maxsize=1)
def build_jwks() -> dict:
    """Build the JWKS from the configured Epic signing keys (staging + prod).

    Cached for the process lifetime — keys don't change at runtime; restart (or
    redeploy) after rotating a key. Keys are taken from the inline PEM env vars
    when set, else the file paths. Missing/unreadable keys are skipped so a
    partially-configured environment still serves what it can; identical keys
    (same PEM + kid) are de-duplicated.
    """
    candidates = [
        (settings.EPIC_STAGING_PRIVATE_KEY, settings.EPIC_STAGING_PRIVATE_KEY_PATH, settings.EPIC_STAGING_JWKS_KID),
        (settings.EPIC_PROD_PRIVATE_KEY, settings.EPIC_PROD_PRIVATE_KEY_PATH, settings.EPIC_PROD_JWKS_KID),
    ]
    keys = []
    seen = set()
    for inline, path, kid in candidates:
        if not kid:
            continue
        try:
            pem = resolve_private_key_pem(inline, path)
        except OSError as exc:
            logger.warning("JWKS: skipping kid=%s (%s)", kid, exc)
            continue
        if not pem or (pem, kid) in seen:
            continue
        seen.add((pem, kid))
        try:
            keys.append(_public_jwk(pem, kid))
        except ValueError as exc:
            logger.warning("JWKS: skipping kid=%s (%s)", kid, exc)
    return {"keys": keys}


class JwksView(APIView):
    """GET /epic/.well-known/jwks.json — public signing keys for token-auth verification."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        resp = Response(build_jwks())
        resp["Cache-Control"] = "public, max-age=3600"
        return resp
