"""Tests for /healthex/* HTTP surface.

Two hard rules the fixtures enforce:

- **Repositories via abstract base + in-memory fake.** Route handlers
  depend on `BaseHealthExLinksRepository` (see
  `app/healthex_routers.py:get_healthex_links_repo`). Tests inject
  `InMemoryHealthExLinksRepository`, which subclasses the ABC. If the
  base signature drifts (e.g. `update_status` gains a required param)
  Python raises `TypeError` at instantiation — tests fail loudly, not
  silently.
- **Airflow client via `create_autospec(BaseAirflowClient, instance=True,
  spec_set=True)`.** `spec_set=True` blocks setting attributes that don't
  exist on the base; `create_autospec` matches the signature of every
  method (so calling `create_dag_run(bogus=1)` raises `TypeError` in the
  test, matching what a real caller would see). Async methods return
  `AsyncMock` automatically (Python 3.8+). This catches drift on the
  Airflow client interface without touching a live Airflow.
"""
from datetime import datetime, timedelta, timezone
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
    """Autospec of the abstract base — signature drift breaks tests loudly."""
    mock = create_autospec(BaseAirflowClient, instance=True, spec_set=True)
    mock.create_dag_run.return_value = "healthex-run-abc123"
    return mock


@pytest.fixture
def healthex_client_mock() -> HealthExClient:
    """Autospec of the HealthEx client for tests that don't exercise its calls.

    FastAPI resolves all endpoint dependencies before the handler runs, so
    even routes that bail on 404/409 need this in app.state. Autospec (not
    a hand fake) so any signature drift on the concrete client — new
    kwarg on `pull_everything`, renamed method — surfaces immediately.
    """
    return create_autospec(HealthExClient, instance=True, spec_set=True)


@pytest.fixture
def healthex_app(
    token_verifier, links_repo, airflow_mock, healthex_client_mock,
) -> FastAPI:
    """FastAPI app wired for the /healthex/* routes only.

    Not shared with the Epic-side `app` fixture in conftest.py because
    that one bakes in the Epic router + its DI overrides. Keeping this
    isolated makes signature/dependency changes to one router incapable
    of breaking the other's tests.
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

class TestIngest:
    async def test_happy_path_initial_returns_202_and_triggers_dag(
        self, http, bearer, links_repo, airflow_mock,
    ) -> None:
        await _seed_link(links_repo, patient_id=PATIENT_ID)

        resp = await http.post(
            f"/healthex/connections/{PROJECT_ID}/ingest", headers=bearer,
        )

        assert resp.status_code == 202
        body = resp.json()
        assert body == {
            "project_id": PROJECT_ID,
            "dag_run_id": "healthex-run-abc123",
        }
        airflow_mock.create_dag_run.assert_awaited_once()
        (_, kwargs) = airflow_mock.create_dag_run.call_args
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

    async def test_incremental_when_last_synced_at_set(
        self, http, bearer, links_repo, airflow_mock,
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

    async def test_404_when_no_link(self, http, bearer, airflow_mock) -> None:
        resp = await http.post(
            f"/healthex/connections/{PROJECT_ID}/ingest", headers=bearer,
        )
        assert resp.status_code == 404
        airflow_mock.create_dag_run.assert_not_awaited()

    async def test_409_when_patient_id_not_yet_resolved(
        self, http, bearer, links_repo, airflow_mock,
    ) -> None:
        # Consent still pending — patient_id is None.
        await _seed_link(
            links_repo, patient_id=None, status=STATUS_PENDING_CONSENT,
        )

        resp = await http.post(
            f"/healthex/connections/{PROJECT_ID}/ingest", headers=bearer,
        )

        assert resp.status_code == 409
        # DAG must not be triggered — the DAG requires healthex_patient_id.
        airflow_mock.create_dag_run.assert_not_awaited()

    async def test_502_when_airflow_trigger_fails(
        self, http, bearer, links_repo, airflow_mock,
    ) -> None:
        await _seed_link(links_repo, patient_id=PATIENT_ID)
        airflow_mock.create_dag_run.side_effect = AirflowError(
            "Airflow unavailable", url="http://airflow/test", method="post",
        )

        resp = await http.post(
            f"/healthex/connections/{PROJECT_ID}/ingest", headers=bearer,
        )

        assert resp.status_code == 502
        assert "Airflow" in resp.json()["detail"]

    async def test_401_when_no_bearer_token(
        self, http, links_repo, airflow_mock,
    ) -> None:
        await _seed_link(links_repo, patient_id=PATIENT_ID)

        resp = await http.post(f"/healthex/connections/{PROJECT_ID}/ingest")

        assert resp.status_code == 401
        airflow_mock.create_dag_run.assert_not_awaited()

    async def test_autospec_rejects_bogus_kwargs_to_create_dag_run(
        self, airflow_mock,
    ) -> None:
        """Regression guard: `create_autospec` must enforce the signature.

        If someone loosens the abstract base's `create_dag_run` (e.g. adds
        **kwargs), this test breaks — forcing the base contract discussion
        to happen before the drift lands in production.
        """
        with pytest.raises(TypeError):
            await airflow_mock.create_dag_run(
                dag="x", dag_run_prefix="y", conf={}, extra_arg="nope",
            )


# ---------------------------------------------------------------------- #
# POST /healthex/connections/{project_id}/refresh                        #
# ---------------------------------------------------------------------- #
# `refresh` is the sibling endpoint that does an in-process pull; these
# tests only cover the DI branches that don't require a HealthExClient
# call (the pull path itself lives in services/healthex_client.py and
# has its own tests). Purpose: catch regressions where the 404/409 gates
# drift out of sync between /ingest and /refresh.

class TestRefreshGates:
    async def test_404_when_no_link(self, http, bearer) -> None:
        resp = await http.post(
            f"/healthex/connections/{PROJECT_ID}/refresh", headers=bearer,
        )
        assert resp.status_code == 404

    async def test_409_when_patient_id_not_yet_resolved(
        self, http, bearer, links_repo,
    ) -> None:
        await _seed_link(
            links_repo, patient_id=None, status=STATUS_PENDING_CONSENT,
        )
        resp = await http.post(
            f"/healthex/connections/{PROJECT_ID}/refresh", headers=bearer,
        )
        assert resp.status_code == 409
