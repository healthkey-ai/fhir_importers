"""Tests for GET /epic/.well-known/jwks.json."""
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import override_settings
from rest_framework.test import APIClient

from apps.epic import jwks


@pytest.fixture
def key_file(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "epic_test.key"
    path.write_bytes(pem)
    return str(path)


def test_jwks_endpoint_is_public_and_serves_configured_key(key_file):
    jwks.build_jwks.cache_clear()
    with override_settings(
        EPIC_STAGING_PRIVATE_KEY_PATH=key_file,
        EPIC_STAGING_JWKS_KID="epic-staging-1",
        EPIC_PROD_PRIVATE_KEY_PATH="",
        EPIC_PROD_JWKS_KID="",
    ):
        resp = APIClient().get("/epic/.well-known/jwks.json")  # no auth

    assert resp.status_code == 200
    keys = resp.json()["keys"]
    assert len(keys) == 1
    jwk = keys[0]
    assert jwk["kid"] == "epic-staging-1"
    assert jwk["kty"] == "RSA"
    assert jwk["use"] == "sig"
    assert jwk["alg"] == "RS256"
    # Only public material — never the private exponent.
    assert "d" not in jwk and "p" not in jwk
    jwks.build_jwks.cache_clear()


def test_jwks_dedupes_and_skips_missing(key_file):
    jwks.build_jwks.cache_clear()
    # Same file+kid for staging and prod → one entry; a missing file is skipped.
    with override_settings(
        EPIC_STAGING_PRIVATE_KEY_PATH=key_file,
        EPIC_STAGING_JWKS_KID="shared",
        EPIC_PROD_PRIVATE_KEY_PATH=key_file,
        EPIC_PROD_JWKS_KID="shared",
    ):
        assert len(jwks.build_jwks()["keys"]) == 1
    jwks.build_jwks.cache_clear()

    with override_settings(
        EPIC_STAGING_PRIVATE_KEY_PATH="/no/such/key", EPIC_STAGING_JWKS_KID="x",
        EPIC_PROD_PRIVATE_KEY_PATH="", EPIC_PROD_JWKS_KID="",
    ):
        assert jwks.build_jwks()["keys"] == []
    jwks.build_jwks.cache_clear()
