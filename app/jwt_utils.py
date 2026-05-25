import time
import uuid
from pathlib import Path

import jwt


def build_client_assertion(
    client_id: str,
    token_endpoint: str,
    private_key_pem_path: str,
    kid: str,
) -> str:
    # aud MUST be the exact token endpoint URL.
    # https://fhir.epic.com/Documentation?docId=oauth2&section=JWKS-URLS
    now = int(time.time())
    payload = {
        "iss": client_id,
        "sub": client_id,
        "aud": token_endpoint,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + 240,
    }
    headers = {"alg": "RS256", "kid": kid}
    key = Path(private_key_pem_path).read_text()
    return jwt.encode(payload, key, algorithm="RS256", headers=headers)
