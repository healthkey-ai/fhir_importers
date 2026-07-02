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


async def test_reconcile_401_when_no_bearer_token(
    http, links_repo, airflow_mock,
) -> None:
    await _seed_link(links_repo, patient_id=PATIENT_ID)

    resp = await http.post(f"/healthex/connections/{PROJECT_ID}/reconcile")

    assert resp.status_code == 401
    airflow_mock.create_dag_run.assert_not_awaited()
