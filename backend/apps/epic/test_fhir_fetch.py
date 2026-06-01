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


# --------------------- per-resource compartment fetch -------------------- #
def _search_bundle(resource, n=1, next_url=None):
    b = {"resourceType": "Bundle", "type": "searchset",
         "entry": [{"resource": {"resourceType": resource}} for _ in range(n)]}
    if next_url:
        b["link"] = [{"relation": "next", "url": next_url}]
    return b


def test_fetch_compartment_collects_resources_and_paginates():
    # Order: Patient read, Observation(lab) [paginated], Observation(vitals),
    # Condition, MedicationRequest.
    http = _FakeHttp([
        _Resp({"resourceType": "Patient", "id": "PAT123"}),
        _Resp(_search_bundle("Observation", n=1, next_url="https://fhir.example/obs-2")),
        _Resp(_search_bundle("Observation", n=1)),                 # page 2 (lab)
        _Resp(_search_bundle("Observation", n=0)),                 # vitals: none
        _Resp(_search_bundle("Condition", n=1)),
        _Resp(_search_bundle("MedicationRequest", n=2)),
    ])

    bundle = EpicFhirClient(http, "tok").fetch_patient_compartment(
        "https://fhir.example/R4", "PAT123",
    )

    types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert types.count("Patient") == 1
    assert types.count("Observation") == 2          # 1 lab page1 + 1 lab page2
    assert types.count("Condition") == 1
    assert types.count("MedicationRequest") == 2
    assert bundle["type"] == "collection"
    assert http.calls[0].endswith("/Patient/PAT123")
    assert "Observation?" in http.calls[1] and "category=laboratory" in http.calls[1]
    assert http.calls[2] == "https://fhir.example/obs-2"          # pagination followed


def test_fetch_requires_patient_id():
    with pytest.raises(EpicFhirError):
        EpicFhirClient(_FakeHttp([]), "tok").fetch_patient_compartment("https://fhir", "")


def test_fetch_tolerates_per_resource_errors():
    # Patient ok, Observation(lab) 404 → skipped, rest ok. Sync still returns data.
    http = _FakeHttp([
        _Resp({"resourceType": "Patient", "id": "PAT"}),
        _Resp({"resourceType": "OperationOutcome"}, status=404),   # lab search fails
        _Resp(_search_bundle("Observation", n=1)),                 # vitals ok
        _Resp(_search_bundle("Condition", n=1)),
        _Resp(_search_bundle("MedicationRequest", n=0)),
    ])
    bundle = EpicFhirClient(http, "tok").fetch_patient_compartment("https://fhir/R4", "PAT")
    types = sorted(e["resource"]["resourceType"] for e in bundle["entry"])
    assert types == ["Condition", "Observation", "Patient"]


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
