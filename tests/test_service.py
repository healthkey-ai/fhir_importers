import urllib.parse

import pytest

from app.client import EpicTokens, SmartConfiguration
from app.organizations import UnknownOrganization
from app.service import InvalidStateError
from app.state_store import PendingState


def _smart() -> SmartConfiguration:
    return SmartConfiguration(
        authorization_endpoint="https://epic.example/oauth2/authorize",
        token_endpoint="https://epic.example/oauth2/token",
        issuer="https://epic.example",
        jwks_uri="https://epic.example/.well-known/jwks.json",
    )


async def test_start_builds_authorize_url_and_persists_state(
    service, epic_client, state_store, organizations
):
    org = organizations.get("example_hospital")
    epic_client.set_smart_configuration(org.endpoint_url, _smart())

    result = await service.start("example_hospital")

    # URL targets the SMART authorization_endpoint with code_challenge + PKCE method.
    parsed = urllib.parse.urlparse(result.authorization_url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "epic.example"
    assert parsed.path == "/oauth2/authorize"
    params = dict(urllib.parse.parse_qsl(parsed.query))
    assert params["response_type"] == "code"
    assert params["code_challenge_method"] == "S256"
    assert params["state"] == result.state
    assert params["client_id"] == "prod-cid"
    assert params["aud"] == org.endpoint_url
    assert len(params["code_challenge"]) > 0

    # The state was stored so /finish can pick it up.
    pending = await state_store.pop(result.state)
    assert pending is not None
    assert pending.organization_alias == "example_hospital"
    assert pending.token_endpoint == "https://epic.example/oauth2/token"


async def test_start_uses_staging_config_for_sandbox_alias(
    service, epic_client, state_store, organizations
):
    sandbox = organizations.get("my_chart_central")
    epic_client.set_smart_configuration(sandbox.endpoint_url, _smart())

    result = await service.start("my_chart_central")
    params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(result.authorization_url).query))
    # The staging-only sandbox alias must resolve to the staging client_id.
    assert params["client_id"] == "staging-cid"


async def test_start_unknown_organization_raises(service):
    with pytest.raises(UnknownOrganization):
        await service.start("does-not-exist")


async def test_finish_unknown_state_raises(service):
    with pytest.raises(InvalidStateError):
        await service.finish(code="ignored", state="unknown")


async def test_finish_consumes_state_exchanges_code_and_returns_tokens(
    service, epic_client, state_store
):
    await state_store.put(
        "st-xyz",
        PendingState(
            code_verifier="cv-123",
            token_endpoint="https://epic.example/oauth2/token",
            organization_alias="example_hospital",
        ),
    )
    epic_client.set_token_response(
        EpicTokens(
            access_token="AT-1",
            refresh_token="RT-1",
            id_token=None,
            expires_in=3600,
            scope="patient/*.read",
            patient="P-42",
        )
    )

    result = await service.finish(code="auth-code-1", state="st-xyz")

    assert result.organization_alias == "example_hospital"
    assert result.access_token == "AT-1"
    assert result.refresh_token == "RT-1"
    assert result.patient == "P-42"
    assert result.scope == "patient/*.read"
    # State is single-use; a second /finish for the same state must fail.
    with pytest.raises(InvalidStateError):
        await service.finish(code="auth-code-1", state="st-xyz")

    # The token-exchange call carried the PKCE verifier + the (injected) assertion.
    [call] = epic_client.exchange_calls
    assert call["code"] == "auth-code-1"
    assert call["code_verifier"] == "cv-123"
    assert call["client_assertion"] == "test-client-assertion"
    assert call["token_endpoint"] == "https://epic.example/oauth2/token"
