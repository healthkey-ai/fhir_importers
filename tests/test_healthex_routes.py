"""Tests for /healthex/* HTTP surface.

Route dependencies are injected as an in-memory fake of the repository
ABC and an autospec of BaseAirflowClient — see fixture docstrings for
what each choice buys.
"""
from datetime import datetime, timezone
from typing import AsyncIterator
from unittest.mock import create_autospec

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.airflow import AirflowError, BaseAirflowClient
from app.healthex_links import (
    STATUS_PENDING_CONSENT,
    STATUS_RETRIEVAL_IN_PROGRESS,
    BaseHealthExLinksRepository,
)
from app.healthex_routers import get_healthex_links_repo, router as healthex_router
from services.healthex_client import HealthExClient

from .fakes import InMemoryHealthExLinksRepository


PROJECT_ID = "2f1c41d6-3752-4e30-b3ca-be78b8c828da"
PATIENT_ID = "52a4f0f2-422e-4160-8350-096fcced82a8"
UID = "test-uid"


@pytest.fixture
def links_repo() -> InMemoryHealthExLinksRepository:
    return InMemoryHealthExLinksRepository()


@pytest.fixture
def airflow_mock() -> BaseAirflowClient:
    """Autospec of the abstract base.

    `create_autospec(..., instance=True, spec_set=True)` enforces the ABC's
    method signatures at test time: a typo in `create_dag_run(bogus=1)`
    raises TypeError in the test, matching real-caller behaviour. Async
    methods get AsyncMocks automatically (Python 3.8+).
    """
    mock = create_autospec(BaseAirflowClient, instance=True, spec_set=True)
    mock.create_dag_run.return_value = "healthex-run-abc123"
    return mock


@pytest.fixture
def healthex_client_mock() -> HealthExClient:
    """Autospec of the HealthEx client.

    FastAPI resolves every endpoint dep before dispatch, so 404/409 paths
    also need this in `app.state`. Autospec (not a hand-rolled fake) so
    signature drift on `pull_everything` etc. surfaces immediately.
    """
    return create_autospec(HealthExClient, instance=True, spec_set=True)


@pytest.fixture
def healthex_app(
    token_verifier, links_repo, airflow_mock, healthex_client_mock,
) -> FastAPI:
    """FastAPI app wired for the /healthex/* routes only.

    Scoped rather than extending conftest's Epic `app` fixture so signature
    or dep changes on one router can't silently break the other's tests.
    """
    app = FastAPI()
    app.include_router(healthex_router)
    app.state.token_verifier = token_verifier
    app.state.airflow_client = airflow_mock
    app.state.healthex_client = healthex_client_mock

    async def _override_repo() -> AsyncIterator[BaseHealthExLinksRepository]:
        yield links_repo

    app.dependency_overrides[get_healthex_links_repo] = _override_repo
    return app


@pytest_asyncio.fixture
async def http(healthex_app) -> AsyncClient:
    transport = ASGITransport(app=healthex_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _seed_link(
    repo: InMemoryHealthExLinksRepository,
    *,
    patient_id: str | None,
    last_synced_at: datetime | None = None,
    status: str = STATUS_RETRIEVAL_IN_PROGRESS,
) -> None:
    await repo.upsert(
        user_uid=UID,
        project_id=PROJECT_ID,
        external_id=UID,
        healthex_patient_id=patient_id,
        status=status,
        onboarding_url=None,
    )
    if last_synced_at is not None:
        await repo.update_status(
            user_uid=UID, project_id=PROJECT_ID,
            status=status, synced_at=last_synced_at,
        )


# ---------------------------------------------------------------------- #
# POST /healthex/connections/{project_id}/ingest                         #
# ---------------------------------------------------------------------- #

async def test_ingest_happy_path_initial(
    http, bearer, links_repo, airflow_mock,
) -> None:
    await _seed_link(links_repo, patient_id=PATIENT_ID)

    resp = await http.post(
        f"/healthex/connections/{PROJECT_ID}/ingest", headers=bearer,
    )

    assert resp.status_code == 202
    assert resp.json() == {
        "project_id": PROJECT_ID,
        "dag_run_id": "healthex-run-abc123",
    }
    airflow_mock.create_dag_run.assert_awaited_once()
    kwargs = airflow_mock.create_dag_run.call_args.kwargs
    assert kwargs["dag"] == "healthex_extract"
    assert kwargs["dag_run_prefix"] == f"{UID}__{PROJECT_ID}"
    assert kwargs["conf"] == {
        "user_uid": UID,
        "project_id": PROJECT_ID,
        "healthex_patient_id": PATIENT_ID,
        "external_id": UID,
        "sync_mode": "initial",
        "since": None,
    }


async def test_ingest_incremental_when_last_synced_at_set(
    http, bearer, links_repo, airflow_mock,
) -> None:
    last_synced = datetime(2026, 6, 30, 12, 0, 0, tzinfo=timezone.utc)
    await _seed_link(
        links_repo, patient_id=PATIENT_ID, last_synced_at=last_synced,
    )

    resp = await http.post(
        f"/healthex/connections/{PROJECT_ID}/ingest", headers=bearer,
    )

    assert resp.status_code == 202
    conf = airflow_mock.create_dag_run.call_args.kwargs["conf"]
    assert conf["sync_mode"] == "incremental"
    assert conf["since"] == last_synced.isoformat()


async def test_ingest_404_when_no_link(http, bearer, airflow_mock) -> None:
    resp = await http.post(
        f"/healthex/connections/{PROJECT_ID}/ingest", headers=bearer,
    )
    assert resp.status_code == 404
    airflow_mock.create_dag_run.assert_not_awaited()


async def test_ingest_409_when_patient_id_not_yet_resolved(
    http, bearer, links_repo, airflow_mock,
) -> None:
    await _seed_link(links_repo, patient_id=None, status=STATUS_PENDING_CONSENT)

    resp = await http.post(
        f"/healthex/connections/{PROJECT_ID}/ingest", headers=bearer,
    )

    assert resp.status_code == 409
    airflow_mock.create_dag_run.assert_not_awaited()


async def test_ingest_502_when_airflow_trigger_fails(
    http, bearer, links_repo, airflow_mock,
) -> None:
    await _seed_link(links_repo, patient_id=PATIENT_ID)
    airflow_mock.create_dag_run.side_effect = AirflowError(
        "Airflow unavailable", url="http://airflow.internal:8080", method="post",
    )

    resp = await http.post(
        f"/healthex/connections/{PROJECT_ID}/ingest", headers=bearer,
    )

    assert resp.status_code == 502
    # Generic message only — internal URL must NOT leak to the client.
    detail = resp.json()["detail"]
    assert detail == "Airflow trigger failed"
    assert "airflow.internal" not in detail


async def test_ingest_401_when_no_bearer_token(
    http, links_repo, airflow_mock,
) -> None:
    await _seed_link(links_repo, patient_id=PATIENT_ID)

    resp = await http.post(f"/healthex/connections/{PROJECT_ID}/ingest")

    assert resp.status_code == 401
    airflow_mock.create_dag_run.assert_not_awaited()


# ---------------------------------------------------------------------- #
# POST /healthex/connections/{project_id}/reconcile                      #
# ---------------------------------------------------------------------- #
# Sibling of /ingest — fires the healthex_reconcile DAG for a single row.
# Not gated on patient_id (unlike /ingest) — reconcile is what resolves
# PENDING_CONSENT rows.

async def test_reconcile_happy_path_row_with_patient_id(
    http, bearer, links_repo, airflow_mock,
) -> None:
    await _seed_link(links_repo, patient_id=PATIENT_ID)

    resp = await http.post(
        f"/healthex/connections/{PROJECT_ID}/reconcile", headers=bearer,
    )

    assert resp.status_code == 202
    assert resp.json() == {
        "project_id": PROJECT_ID,
        "dag_run_id": "healthex-run-abc123",
        "debounced": False,
    }
    airflow_mock.create_dag_run.assert_awaited_once()
    kwargs = airflow_mock.create_dag_run.call_args.kwargs
    assert kwargs["dag"] == "healthex_reconcile"
    assert kwargs["dag_run_prefix"] == f"{UID}__{PROJECT_ID}"
    # Reconcile conf carries only identifiers — no sync_mode, no since,
    # no patient_id (the DAG resolves those from getPatientConsents).
    assert kwargs["conf"] == {"user_uid": UID, "project_id": PROJECT_ID}


async def test_reconcile_happy_path_pending_consent_row(
    http, bearer, links_repo, airflow_mock,
) -> None:
    """A PENDING_CONSENT row (patient_id is None) must still trigger the DAG.
    This is the primary callback-flow use case — the reconcile is what
    resolves the patient_id and transitions the row."""
    await _seed_link(
        links_repo, patient_id=None, status=STATUS_PENDING_CONSENT,
    )

    resp = await http.post(
        f"/healthex/connections/{PROJECT_ID}/reconcile", headers=bearer,
    )

    assert resp.status_code == 202
    airflow_mock.create_dag_run.assert_awaited_once()


async def test_reconcile_404_when_no_link(
    http, bearer, airflow_mock,
) -> None:
    resp = await http.post(
        f"/healthex/connections/{PROJECT_ID}/reconcile", headers=bearer,
    )
    assert resp.status_code == 404
    airflow_mock.create_dag_run.assert_not_awaited()


async def test_reconcile_502_when_airflow_trigger_fails(
    http, bearer, links_repo, airflow_mock,
) -> None:
    await _seed_link(links_repo, patient_id=PATIENT_ID)
    airflow_mock.create_dag_run.side_effect = AirflowError(
        "Airflow unavailable",
        url="http://airflow.internal:8080", method="post",
    )

    resp = await http.post(
        f"/healthex/connections/{PROJECT_ID}/reconcile", headers=bearer,
    )

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail == "Airflow trigger failed"
    # Guard: internal Airflow host name must not leak in the client response.
    assert "airflow.internal" not in detail


async def test_reconcile_debounced_when_polled_recently(
    http, bearer, links_repo, airflow_mock,
) -> None:
    """Backend-side rate limit: if last_status_polled_at is < 30s old, the
    reconcile endpoint returns 202 with dag_run_id=null + debounced=true
    and does NOT fire the DAG. Guards against rapid page refresh spawning
    N tasks."""
    now = datetime.now(timezone.utc)
    await _seed_link(links_repo, patient_id=PATIENT_ID, last_synced_at=None)
    # Fake a recent poll on the row (5 seconds ago).
    await links_repo.update_status(
        user_uid=UID, project_id=PROJECT_ID,
        status=STATUS_RETRIEVAL_IN_PROGRESS,
        polled_at=now,
    )

    resp = await http.post(
        f"/healthex/connections/{PROJECT_ID}/reconcile", headers=bearer,
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["project_id"] == PROJECT_ID
    assert body["debounced"] is True
    assert body["dag_run_id"] is None
    # Critical: no DAG run must have been triggered.
    airflow_mock.create_dag_run.assert_not_awaited()


# ---------------------------------------------------------------------- #
# _attach_redirect_uri helper                                            #
# ---------------------------------------------------------------------- #
# The backend-side redirectUri attachment. Frontend sends a plain URI;
# backend encodes it as HealthEx expects. Query-param name lives here
# only — never on the frontend or the DB.

def test_attach_redirect_uri_none_returns_url_unchanged() -> None:
    from app.healthex_routers import _attach_redirect_uri
    result = _attach_redirect_uri("https://healthex.io/onboarding?xid=abc", None)
    assert result == "https://healthex.io/onboarding?xid=abc"


def test_attach_redirect_uri_appends_when_query_already_present() -> None:
    from app.healthex_routers import _attach_redirect_uri
    result = _attach_redirect_uri(
        "https://healthex.io/onboarding?xid=abc",
        "https://ht-phr-staging.run.app/connect/records",
    )
    # Order not guaranteed by parse_qsl round-trip — assert both present.
    assert "xid=abc" in result
    assert "redirectUri=https%3A%2F%2Fht-phr-staging.run.app%2Fconnect%2Frecords" in result


def test_attach_redirect_uri_appends_when_no_query() -> None:
    from app.healthex_routers import _attach_redirect_uri
    result = _attach_redirect_uri(
        "https://healthex.io/onboarding",
        "https://ht-phr.example/connect/records",
    )
    assert result.startswith("https://healthex.io/onboarding?")
    assert "redirectUri=https%3A%2F%2Fht-phr.example%2Fconnect%2Frecords" in result


def test_attach_redirect_uri_overrides_prior_redirect_uri_param() -> None:
    """Idempotency guard — a re-mint on the same row must not double-append."""
    from app.healthex_routers import _attach_redirect_uri
    result = _attach_redirect_uri(
        "https://healthex.io/onboarding?xid=abc&redirectUri=old",
        "https://new.example/records",
    )
    assert result.count("redirectUri=") == 1
    assert "redirectUri=https%3A%2F%2Fnew.example%2Frecords" in result


async def test_reconcile_401_when_no_bearer_token(
    http, links_repo, airflow_mock,
) -> None:
    await _seed_link(links_repo, patient_id=PATIENT_ID)

    resp = await http.post(f"/healthex/connections/{PROJECT_ID}/reconcile")

    assert resp.status_code == 401
    airflow_mock.create_dag_run.assert_not_awaited()


# ---------------------------------------------------------------------- #
# GET /healthex/connections/{project_id}/status                          #
# ---------------------------------------------------------------------- #
# Post-migration: /status returns the DB row + refreshes polled_at. No
# HealthEx round-trip; reconciliation is owned by the healthex_reconcile
# DAG. Guards are here so nobody accidentally re-adds a HealthEx call
# (which would defeat the whole "reconcile happens in Airflow" split).

async def test_status_returns_db_state_without_hitting_healthex(
    http, bearer, links_repo, healthex_client_mock,
) -> None:
    await _seed_link(links_repo, patient_id=PATIENT_ID)

    resp = await http.get(
        f"/healthex/connections/{PROJECT_ID}/status", headers=bearer,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == PROJECT_ID
    assert body["healthex_patient_id"] == PATIENT_ID
    assert body["status"] == STATUS_RETRIEVAL_IN_PROGRESS
    assert body["polled_at"] is not None
    # Critical invariant: NO calls to the HealthExClient. If someone
    # re-adds a get_consent_state / get_data_retrieval_status call here,
    # this fails.
    healthex_client_mock.get_consent_state.assert_not_called()
    healthex_client_mock.get_data_retrieval_status.assert_not_called()


async def test_status_advances_polled_at_on_each_call(
    http, bearer, links_repo,
) -> None:
    await _seed_link(links_repo, patient_id=PATIENT_ID)

    first = await http.get(
        f"/healthex/connections/{PROJECT_ID}/status", headers=bearer,
    )
    # Small non-zero gap; the endpoint uses datetime.now() under the hood
    # and the fake repo persists whatever we hand in.
    second = await http.get(
        f"/healthex/connections/{PROJECT_ID}/status", headers=bearer,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["polled_at"] != second.json()["polled_at"], (
        "polled_at must advance on every /status call so the frontend can "
        "detect a completed reconcile-DAG run"
    )


async def test_status_404_when_no_link(http, bearer) -> None:
    resp = await http.get(
        f"/healthex/connections/{PROJECT_ID}/status", headers=bearer,
    )
    assert resp.status_code == 404
