"""SMART on FHIR private_key_jwt client assertion builder.

Hardened port of the inline JWT builder in `epic.py`. Signs a short-lived
RS256 JWT proving the client owns the private key that pairs with the
public JWK Epic/Cerner has at our JWKS URL.

Spec: https://www.hl7.org/fhir/smart-app-launch/client-confidential-asymmetric.html
"""
from __future__ import annotations

import datetime
import logging
import uuid

import jwt

_logger = logging.getLogger(__name__)

# Per the SMART spec: the assertion's `exp` MUST be no more than 5 minutes
# past `iat`. 4 minutes leaves a buffer for clock skew.
_ASSERTION_LIFETIME_SECONDS = 240


def build_client_assertion(
    *,
    client_id: str,
    token_endpoint: str,
    private_key_pem: str,
    kid: str,
    algorithm: str = "RS256",
) -> str:
    """Return a signed JWT suitable for `client_assertion=<jwt>` at the
    SMART token endpoint.

    Args:
        client_id: app's client_id (becomes `iss` AND `sub`).
        token_endpoint: EHR's /oauth2/token URL — must match exactly; this
            is the `aud` claim that EHRs validate strictly.
        private_key_pem: PEM-encoded private key text (contents of file).
        kid: key id; must exist in our published JWKS so the EHR can pick
            the right public key for verification.
        algorithm: RS256 is the SMART default. ES384 also supported.
    """
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    payload = {
        "iss": client_id,
        "sub": client_id,
        "aud": token_endpoint,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + _ASSERTION_LIFETIME_SECONDS,
    }
    headers = {"alg": algorithm, "kid": kid, "typ": "JWT"}
    return jwt.encode(payload, private_key_pem, algorithm=algorithm, headers=headers)
