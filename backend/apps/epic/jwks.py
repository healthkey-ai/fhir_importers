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
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from django.conf import settings
from jwt.algorithms import RSAAlgorithm
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


def _public_jwk(private_key_path: str, kid: str) -> dict:
    key = load_pem_private_key(Path(private_key_path).read_bytes(), password=None)
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return jwk


@lru_cache(maxsize=1)
def build_jwks() -> dict:
    """Build the JWKS from the configured Epic signing keys (staging + prod).

    Cached for the process lifetime — keys don't change at runtime; restart (or
    redeploy) after rotating a key. Missing/unreadable key files are skipped so
    a partially-configured environment still serves what it can.
    """
    candidates = [
        (settings.EPIC_STAGING_PRIVATE_KEY_PATH, settings.EPIC_STAGING_JWKS_KID),
        (settings.EPIC_PROD_PRIVATE_KEY_PATH, settings.EPIC_PROD_JWKS_KID),
    ]
    keys = []
    seen = set()
    for path, kid in candidates:
        if not path or not kid or (path, kid) in seen:
            continue
        seen.add((path, kid))
        try:
            keys.append(_public_jwk(path, kid))
        except (OSError, ValueError) as exc:
            logger.warning("JWKS: skipping key %s (kid=%s): %s", path, kid, exc)
    return {"keys": keys}


class JwksView(APIView):
    """GET /epic/.well-known/jwks.json — public signing keys for token-auth verification."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        resp = Response(build_jwks())
        resp["Cache-Control"] = "public, max-age=3600"
        return resp
