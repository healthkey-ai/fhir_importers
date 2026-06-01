from datetime import datetime, timedelta, timezone

from app.client import EpicTokens, SmartConfiguration
from app.state_store import PendingState


def _smart() -> SmartConfiguration:
    return SmartConfiguration(
        authorization_endpoint="https://epic.example/oauth2/authorize",
        token_endpoint="https://epic.example/oauth2/token",
        issuer="https://epic.example",
        jwks_uri="https://epic.example/.well-known/jwks.json",
    )


async def test_health(http_client):
    response = await http_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_list_organizations(http_client):
    response = await http_client.get("/epic/organizations")
    assert response.status_code == 200
    aliases = {o["alias"] for o in response.json()}
    assert aliases == {"my_chart_central", "example_hospital"}


async def test_list_connections_requires_bearer(http_client):
    response = await http_client.get("/epic/connections")
    assert response.status_code == 401


async def test_list_connections_rejects_bad_token(http_client):
    response = await http_client.get(
        "/epic/connections",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


async def test_list_connections_returns_metadata(http_client, connections_repo, bearer):
    await connections_repo.upsert(
        user_uid="test-uid",
        organization_alias="example_hospital",
        access_token="AT",
        refresh_token=None,
        id_token=None,
        scope="patient/*.read",
        patient="P-1",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = await http_client.get("/epic/connections", headers=bearer)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["organization_alias"] == "example_hospital"
    assert body[0]["patient"] == "P-1"


async def test_list_connections_scopes_to_caller_uid(http_client, connections_repo, bearer):
    await connections_repo.upsert(
        user_uid="someone-else",
        organization_alias="example_hospital",
        access_token="AT",
        refresh_token=None,
        id_token=None,
        scope=None,
        patient=None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = await http_client.get("/epic/connections", headers=bearer)
    assert response.status_code == 200
    assert response.json() == []


async def test_delete_missing_connection_returns_404(http_client, bearer):
    response = await http_client.delete("/epic/connections/example_hospital", headers=bearer)
    assert response.status_code == 404


async def test_delete_existing_connection_returns_204(http_client, connections_repo, bearer):
    await connections_repo.upsert(
        user_uid="test-uid",
        organization_alias="example_hospital",
        access_token="AT",
        refresh_token=None,
        id_token=None,
        scope=None,
        patient=None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = await http_client.delete("/epic/connections/example_hospital", headers=bearer)
    assert response.status_code == 204
    assert await connections_repo.list_for_user("test-uid") == []


async def test_auth_start_returns_authorize_url(http_client, epic_client, organizations):
    epic_client.set_smart_configuration(organizations.get("example_hospital").endpoint_url, _smart())
    response = await http_client.post(
        "/epic/auth/start", json={"organization_alias": "example_hospital"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["authorization_url"].startswith("https://epic.example/oauth2/authorize?")
    assert "state" in body and body["state"]


async def test_auth_start_unknown_org_returns_404(http_client):
    response = await http_client.post(
        "/epic/auth/start", json={"organization_alias": "does-not-exist"}
    )
    assert response.status_code == 404


async def test_auth_finish_requires_bearer(http_client):
    response = await http_client.post(
        "/epic/auth/finish", json={"code": "c", "state": "s"}
    )
    assert response.status_code == 401


async def test_auth_finish_invalid_state_returns_400(http_client, bearer):
    response = await http_client.post(
        "/epic/auth/finish",
        json={"code": "c", "state": "never-issued"},
        headers=bearer,
    )
    assert response.status_code == 400


async def test_auth_finish_persists_and_returns_metadata_no_tokens(
    http_client, epic_client, state_store, connections_repo, bearer
):
    await state_store.put(
        "st-1",
        PendingState(
            code_verifier="cv",
            token_endpoint="https://epic.example/oauth2/token",
            organization_alias="example_hospital",
        ),
    )
    epic_client.set_token_response(
        EpicTokens(
            access_token="SECRET-AT",
            refresh_token="SECRET-RT",
            id_token=None,
            expires_in=3600,
            scope="patient/*.read",
            patient="P-99",
        )
    )

    response = await http_client.post(
        "/epic/auth/finish",
        json={"code": "auth-code", "state": "st-1"},
        headers=bearer,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["organization_alias"] == "example_hospital"
    assert body["patient"] == "P-99"
    assert body["status"] == "connected"
    # Metadata-only response; raw tokens must not leak to the client.
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert "SECRET-AT" not in response.text
    assert "SECRET-RT" not in response.text

    stored = await connections_repo.list_for_user("test-uid")
    assert len(stored) == 1
    assert stored[0].organization_alias == "example_hospital"
