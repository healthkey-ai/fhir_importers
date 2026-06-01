"""Phase 3 tests: Epic FHIR fetch ($everything pagination) + token refresh."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.accounts.models import Identity
from apps.epic import fetch
from apps.epic.client import EpicTokens
from apps.epic.fhir_client import EpicFhirClient, EpicFhirError
from apps.epic.models import Connection


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = ""

    def json(self):
        return self._payload


class _FakeHttp:
    """Minimal httpx.Client stand-in returning queued responses."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, headers=None):
        self.calls.append(url)
        return self._responses.pop(0)


@pytest.fixture
def user(db):
    return Identity.objects.create_user(email="fetch@example.com", password="pw-supersecret")


# ----------------------------- $everything ------------------------------- #
def test_fetch_everything_follows_pagination():
    page1 = {
        "resourceType": "Bundle",
        "entry": [{"resource": {"resourceType": "Patient"}}],
        "link": [{"relation": "next", "url": "https://fhir.example/next-page"}],
    }
    page2 = {"resourceType": "Bundle",
             "entry": [{"resource": {"resourceType": "Observation"}}]}
    http = _FakeHttp([_Resp(page1), _Resp(page2)])

    bundle = EpicFhirClient(http, "tok").fetch_patient_everything(
        "https://fhir.example/R4", "PAT123",
    )

    assert len(bundle["entry"]) == 2
    assert bundle["type"] == "collection"
    assert http.calls[0].endswith("/Patient/PAT123/$everything")
    assert http.calls[1] == "https://fhir.example/next-page"


def test_fetch_requires_patient_id():
    with pytest.raises(EpicFhirError):
        EpicFhirClient(_FakeHttp([]), "tok").fetch_patient_everything("https://fhir", "")


def test_fetch_raises_on_http_error():
    http = _FakeHttp([_Resp({"resourceType": "OperationOutcome"}, status=401)])
    with pytest.raises(EpicFhirError):
        EpicFhirClient(http, "tok").fetch_patient_everything("https://fhir", "PAT")


# ----------------------------- token refresh ----------------------------- #
@pytest.mark.django_db
def test_ensure_fresh_token_skips_when_valid(user):
    conn = Connection.objects.create(identity=user, org_alias="org")
    conn.access_token = "GOOD"
    conn.refresh_token = "RT"
    conn.token_expires_at = timezone.now() + timedelta(hours=1)
    conn.save()

    with patch("apps.epic.fetch.EpicClient") as EC:
        token = fetch._ensure_fresh_token(conn)

    assert token == "GOOD"
    EC.assert_not_called()


@pytest.mark.django_db
def test_ensure_fresh_token_refreshes_when_expired(user):
    conn = Connection.objects.create(identity=user, org_alias="my_chart_central")
    conn.access_token = "OLD"
    conn.refresh_token = "RT"
    conn.token_expires_at = timezone.now() - timedelta(hours=1)
    conn.save()

    org = SimpleNamespace(endpoint_url="https://fhir.example/R4")
    epic = SimpleNamespace(client_id="cid", private_key_path="/x.key", jwks_kid="kid")
    smart = SimpleNamespace(token_endpoint="https://token.example")
    new_tokens = EpicTokens(access_token="NEW", refresh_token="RT2", id_token=None,
                            expires_in=3600, scope="patient/*.read", patient=None)

    with patch("apps.epic.fetch.get_auth_service") as gas, \
         patch("apps.epic.fetch.build_client_assertion", return_value="assertion"), \
         patch("apps.epic.fetch.EpicClient") as EC:
        gas.return_value.smart_config_for_org.return_value = (org, epic, smart)
        EC.return_value.refresh_access_token.return_value = new_tokens
        token = fetch._ensure_fresh_token(conn)

    assert token == "NEW"
    conn.refresh_from_db()
    assert conn.access_token == "NEW"
    assert conn.refresh_token == "RT2"  # rotated
    assert conn.token_expires_at > timezone.now()


@pytest.mark.django_db
def test_ensure_fresh_token_no_refresh_token_returns_current(user):
    conn = Connection.objects.create(identity=user, org_alias="org")
    conn.access_token = "STALE"
    conn.token_expires_at = timezone.now() - timedelta(hours=1)
    conn.save()  # no refresh_token

    with patch("apps.epic.fetch.EpicClient") as EC:
        token = fetch._ensure_fresh_token(conn)

    assert token == "STALE"
    EC.assert_not_called()
