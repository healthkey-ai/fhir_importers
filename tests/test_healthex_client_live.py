"""Live smoke tests against the real HealthEx API.

Deliberately outside the DI-mocked test surface — these hit
`api.healthex.io` (or whatever `HEALTHEX_BASE_URL` points at). Skipped
unless `HEALTHEX_API_KEY`/`SECRET`/`PROJECT_ID` are exported. Use them
after credential rotations, cutovers between prod and sandbox tiers, or
when HealthEx claims to have changed something.

Run: `set -a; source .env; set +a && pytest -m external_api`
Skip: default `pytest` invocation excludes `-m external_api` (or should).
"""
import os
import re

import pytest

from services.service_locator import ServiceLocator


_REQUIRED_ENV = ("HEALTHEX_API_KEY", "HEALTHEX_API_SECRET", "HEALTHEX_PROJECT_ID")


pytestmark = [
    pytest.mark.external_api,
    pytest.mark.skipif(
        not all(os.environ.get(k) for k in _REQUIRED_ENV),
        reason=f"Requires env vars: {', '.join(_REQUIRED_ENV)}",
    ),
]


async def test_mint_org_jwt() -> None:
    """The org token endpoint accepts our credentials and returns a JWT.

    The cheapest possible integration check — no patient touched, no
    project state read, just proves the four config pieces (base URL,
    api_key, api_secret, project_id) all match on the vendor's side.
    """
    async with ServiceLocator.healthex_client() as client:
        token = await client.org_jwt()

    assert token, "org_jwt() returned empty"
    parts = token.split(".")
    assert len(parts) == 3, (
        f"Expected a JWT (three dot-separated base64url parts); "
        f"got {len(parts)} parts"
    )


async def test_jwt_claims_carry_organization_id() -> None:
    """Decoded claims include `organizationId` — needed for cross-service traces."""
    async with ServiceLocator.healthex_client() as client:
        claims = await client.jwt_claims()

    org_id = claims.get("organizationId")
    assert org_id, f"jwt_claims missing organizationId; got keys {sorted(claims)}"
    # UUID shape — HealthEx returns lowercase UUIDs; guard against
    # accidental format drift (e.g. numeric IDs) rather than pinning the
    # value, since sandbox and prod orgs differ.
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        org_id,
    ), f"organizationId doesn't look like a UUID: {org_id!r}"


async def test_capability_statement_reachable() -> None:
    """FHIR endpoint answers with a CapabilityStatement.

    Verifies the FHIR sub-domain (not the /v1/* JSON API) accepts our
    bearer token and speaks R4. Cheapest way to catch a broken FHIR-side
    deploy without touching a real patient.
    """
    async with ServiceLocator.healthex_client() as client:
        capabilities = await client.get_capability_statement()

    assert capabilities.get("resourceType") == "CapabilityStatement"
    assert capabilities.get("fhirVersion", "").startswith("4."), (
        f"Expected FHIR R4; got fhirVersion={capabilities.get('fhirVersion')!r}"
    )
