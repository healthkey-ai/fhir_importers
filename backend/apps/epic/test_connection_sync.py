"""Phase 2 connector tests: token encryption, sync task, connection endpoints."""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Identity
from apps.epic import crypto, ctomop_client, tasks
from apps.epic.client import EpicTokens
from apps.epic.models import Connection, SyncJob


@pytest.fixture
def user(db):
    return Identity.objects.create_user(email="patient@example.com", password="pw-supersecret")


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_crypto_roundtrip():
    enc = crypto.encrypt("super-secret-token")
    assert enc != "super-secret-token"
    assert crypto.decrypt(enc) == "super-secret-token"
    assert crypto.decrypt("") == ""


@pytest.mark.django_db
def test_connection_encrypts_tokens_at_rest(user):
    conn = Connection(identity=user, org_alias="my_chart_central")
    conn.access_token = "ACCESS"
    conn.refresh_token = "REFRESH"
    conn.save()

    raw = Connection.objects.values("access_token_enc", "refresh_token_enc").get(pk=conn.pk)
    assert raw["access_token_enc"] not in ("ACCESS", "")
    assert "ACCESS" not in raw["access_token_enc"]  # ciphertext, not plaintext

    fresh = Connection.objects.get(pk=conn.pk)
    assert fresh.access_token == "ACCESS"
    assert fresh.refresh_token == "REFRESH"


@pytest.mark.django_db
def test_run_sync_posts_bundle_and_records_result(user):
    conn = Connection.objects.create(identity=user, org_alias="org")
    job = SyncJob.objects.create(connection=conn)
    fake = ctomop_client.FhirSyncResult(
        person_id=42, measurement_ids=[1], condition_ids=[2], drug_exposure_ids=[],
        demographics_updated=True,
        totals={"measurements": 10, "conditions": 2, "medications": 0},
    )
    bundle = {"resourceType": "Bundle", "entry": [
        {"resource": {"resourceType": "Patient"}},
        {"resource": {"resourceType": "Observation"}},
    ]}
    with patch("apps.epic.tasks.build_bundle_for_connection", return_value=bundle), \
         patch("apps.epic.tasks.ctomop_client.sync_fhir_bundle", return_value=fake) as m:
        tasks.run_sync(job.id)

    job.refresh_from_db()
    assert job.status == SyncJob.SUCCEEDED
    assert job.person_id == 42
    assert job.created_count == 2
    assert job.resources_fetched == 2
    assert job.counts == {"demographics": 1, "measurements": 1, "conditions": 1, "medications": 0}
    assert job.record_totals == {"measurements": 10, "conditions": 2, "medications": 0}
    assert job.finished_at is not None
    # Identity is forwarded as actor_iss/actor_sub (connector stores no person_id).
    kwargs = m.call_args.kwargs
    assert kwargs["actor_iss"] == user.issuer
    assert kwargs["actor_sub"] == user.sub


@pytest.mark.django_db
def test_run_sync_records_failure(user):
    conn = Connection.objects.create(identity=user, org_alias="org")
    job = SyncJob.objects.create(connection=conn)
    bundle = {"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Patient"}}]}
    with patch("apps.epic.tasks.build_bundle_for_connection", return_value=bundle), \
         patch("apps.epic.tasks.ctomop_client.sync_fhir_bundle",
               side_effect=ctomop_client.CtomopSyncError("boom")):
        tasks.run_sync(job.id)
    job.refresh_from_db()
    assert job.status == SyncJob.FAILED
    assert "boom" in job.error

    # A fetch failure is also recorded on the job (not raised).
    job2 = SyncJob.objects.create(connection=conn)
    with patch("apps.epic.tasks.build_bundle_for_connection",
               side_effect=RuntimeError("epic down")):
        tasks.run_sync(job2.id)
    job2.refresh_from_db()
    assert job2.status == SyncJob.FAILED
    assert "epic down" in job2.error


@pytest.mark.django_db
def test_run_sync_posts_in_bounded_chunks(user):
    conn = Connection.objects.create(identity=user, org_alias="org")
    job = SyncJob.objects.create(connection=conn)
    entries = [{"resource": {"resourceType": "Observation"}} for _ in range(900)]
    bundle = {"resourceType": "Bundle", "type": "collection", "entry": entries}
    fake = ctomop_client.FhirSyncResult(
        person_id=7, measurement_ids=[1], condition_ids=[], drug_exposure_ids=[])
    with patch("apps.epic.tasks.build_bundle_for_connection", return_value=bundle), \
         patch("apps.epic.tasks.ctomop_client.sync_fhir_bundle", return_value=fake) as m:
        tasks.run_sync(job.id)

    job.refresh_from_db()
    assert job.status == SyncJob.SUCCEEDED
    assert m.call_count == 3                 # 400 + 400 + 100
    assert job.resources_fetched == 900
    assert job.created_count == 3            # 1 created per chunk × 3 chunks
    assert job.counts == {"demographics": 0, "measurements": 3, "conditions": 0, "medications": 0}
    assert job.person_id == 7
    for call in m.call_args_list:            # every chunk stays under ctomop's limit
        assert len(call.kwargs["bundle"]["entry"]) <= tasks.CHUNK_SIZE


@pytest.mark.django_db
def test_connections_endpoint_is_caller_scoped(api, user):
    Connection.objects.create(identity=user, org_alias="mine")
    other = Identity.objects.create_user(email="other@example.com", password="pw-supersecret")
    Connection.objects.create(identity=other, org_alias="theirs")

    resp = api.get("/epic/connections")
    assert resp.status_code == 200
    assert {c["org_alias"] for c in resp.json()} == {"mine"}


@pytest.mark.django_db
def test_sync_job_poll_own_only(api, user):
    conn = Connection.objects.create(identity=user, org_alias="mine")
    job = SyncJob.objects.create(connection=conn)
    assert api.get(f"/epic/sync/{job.id}").status_code == 200

    other = Identity.objects.create_user(email="o2@example.com", password="pw-supersecret")
    ojob = SyncJob.objects.create(connection=Connection.objects.create(identity=other, org_alias="x"))
    assert api.get(f"/epic/sync/{ojob.id}").status_code == 404


@pytest.mark.django_db
def test_finish_persists_connection_without_leaking_tokens(api, user):
    tokens = EpicTokens(
        access_token="AT", refresh_token="RT", id_token=None,
        expires_in=3600, scope="patient/*.read", patient="ePATIENT",
    )
    with patch("apps.epic.views.get_auth_service") as gas, \
         patch("apps.epic.views.run_sync_task.delay") as delay:
        gas.return_value.finish.return_value = (tokens, "my_chart_central")
        resp = api.post("/epic/auth/finish", {"code": "c", "state": "s"}, format="json")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    # Tokens are never returned to the browser anymore.
    assert "access_token" not in body and "refresh_token" not in body
    assert body["patient"] == "ePATIENT"

    conn = Connection.objects.get(id=body["connection_id"])
    assert conn.identity_id == user.id
    assert conn.access_token == "AT" and conn.refresh_token == "RT"
    assert conn.epic_patient_id == "ePATIENT"
    assert conn.token_expires_at is not None
    assert SyncJob.objects.filter(connection=conn, id=body["sync_job_id"]).exists()
    delay.assert_called_once()
