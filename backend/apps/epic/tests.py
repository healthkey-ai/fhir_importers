"""Phase 0 smoke tests: the Django port boots, identity auth gates the Epic
endpoints, and the organization registry loads.

These intentionally avoid Redis and live Epic calls (those land with the
sync pipeline in Phase 2).
"""
import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api():
    return APIClient()


def test_health_is_open(api):
    resp = api.get("/health/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_organizations_requires_auth(api):
    # Unauthenticated requests are rejected. DRF returns 403 (not 401) here
    # because the PartnerAuthentication→JWT chain exposes no WWW-Authenticate
    # header — same behaviour as hk-labs. Either is "not allowed in".
    resp = api.get("/epic/organizations")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_organizations_lists_after_local_login(api):
    # Standalone-mode local identity → SimpleJWT → resolves to accounts.Identity.
    reg = api.post(
        "/api/v1/auth/register/",
        {"email": "patient@example.com", "password": "s3cret-passw0rd"},
        format="json",
    )
    assert reg.status_code == 201, reg.content
    access = reg.json()["tokens"]["access"]

    api.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    resp = api.get("/epic/organizations")
    assert resp.status_code == 200, resp.content
    aliases = {o["alias"] for o in resp.json()}
    assert "my_chart_central" in aliases
