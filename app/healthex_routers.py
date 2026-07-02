import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .airflow import AirflowError, BaseAirflowClient
from .auth import get_current_user_uid
from services.healthex_client import HealthExClient, HealthExError
from .healthex_links import (
    STATUS_PENDING_CONSENT,
    BaseHealthExLinksRepository,
    HealthExLinksRepository,
)
from .schemas import (
    HealthExConnectRequest,
    HealthExIngestResponse,
    HealthExLinkResponse,
    HealthExReconcileResponse,
    HealthExStatusResponse,
)


HEALTHEX_EXTRACT_DAG = "healthex_extract"
HEALTHEX_RECONCILE_DAG = "healthex_reconcile"


def get_airflow_client(request: Request) -> BaseAirflowClient:
    return request.app.state.airflow_client


def _dag_run_prefix(uid: str, project_id: str) -> str:
    return f"{uid}__{project_id}"


def _dag_conf(
    uid: str,
    project_id: str,
    external_id: str,
    healthex_patient_id: str,
    since_iso: str | None,
) -> dict:
    return {
        "user_uid": uid,
        "project_id": project_id,
        "healthex_patient_id": healthex_patient_id,
        "external_id": external_id,
        "sync_mode": "incremental" if since_iso else "initial",
        "since": since_iso,
    }


_logger = logging.getLogger(__name__)


def get_healthex_client(request: Request) -> HealthExClient:
    return request.app.state.healthex_client


def get_healthex_project_id(request: Request) -> str:
    pid: str = request.app.state.settings.healthex_project_id
    if not pid:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HEALTHEX_PROJECT_ID not configured",
        )
    return pid


async def get_healthex_links_repo(
    request: Request,
) -> AsyncIterator[BaseHealthExLinksRepository]:
    sessionmaker = request.app.state.db_sessionmaker
    async with sessionmaker() as session:
        yield HealthExLinksRepository(session)


router = APIRouter(prefix="/healthex", tags=["healthex"])


@router.get("/connections", response_model=list[HealthExLinkResponse])
async def list_connections(
    uid: str = Depends(get_current_user_uid),
    repo: BaseHealthExLinksRepository = Depends(get_healthex_links_repo),
) -> list[HealthExLinkResponse]:
    return [_to_response(m) for m in await repo.list_for_user(uid)]


@router.post("/connect", response_model=HealthExLinkResponse)
async def connect(
    body: HealthExConnectRequest,
    uid: str = Depends(get_current_user_uid),
    repo: BaseHealthExLinksRepository = Depends(get_healthex_links_repo),
    client: HealthExClient = Depends(get_healthex_client),
    project_id: str = Depends(get_healthex_project_id),
) -> HealthExLinkResponse:
    # Idempotent: re-issuing the link mints a fresh signature each call, so
    # serve the persisted one if we already have a link for this user/project.
    if existing := await repo.get(uid, project_id):
        return _to_response(existing)

    # addPatients creates the Recruitment record HealthEx requires before the
    # Unique Link binds at consent time; without it the patient-side
    # link-identified-patient step returns 404 (empirically verified).
    try:
        await client.add_patient(
            external_id=uid,
            email=body.email,
            first_name=body.first_name or "User",
            last_name=body.last_name or "Account",
            suppress_notifications=True,
        )
        onboarding_url = await client.get_unique_link(external_id=uid)
    except HealthExError as exc:
        _logger.exception("HealthEx connect failed for uid=%s", uid)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"HealthEx upstream error: {exc}",
        ) from exc

    meta = await repo.upsert(
        user_uid=uid,
        project_id=project_id,
        external_id=uid,
        healthex_patient_id=None,
        status=STATUS_PENDING_CONSENT,
        onboarding_url=onboarding_url,
    )
    return _to_response(meta)


@router.delete(
    "/connections/{project_id}", status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_connection(
    project_id: str,
    uid: str = Depends(get_current_user_uid),
    repo: BaseHealthExLinksRepository = Depends(get_healthex_links_repo),
) -> Response:
    if not await repo.delete(uid, project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No HealthEx link for project: {project_id}",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/connections/{project_id}/status", response_model=HealthExStatusResponse,
)
async def poll_status(
    project_id: str,
    uid: str = Depends(get_current_user_uid),
    repo: BaseHealthExLinksRepository = Depends(get_healthex_links_repo),
) -> HealthExStatusResponse:
    """Return the current row state; refresh `last_status_polled_at`.

    Reconciliation with HealthEx ground truth (getPatientConsents + status
    transitions) is now owned by the `healthex_reconcile` Airflow DAG. This
    endpoint used to call HealthEx inline; that path was moved out on the
    same commit that landed the `/reconcile` endpoint. Callers who want a
    fresh reconcile should POST /healthex/connections/{project_id}/reconcile
    and poll this endpoint (or /connections) for the updated row.
    """
    link = await repo.get(uid, project_id)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No HealthEx link for project: {project_id}",
        )

    now = datetime.now(timezone.utc)
    updated = await repo.update_status(
        user_uid=uid, project_id=project_id,
        status=link.status, polled_at=now,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="HealthEx link mutated mid-poll",
        )
    return HealthExStatusResponse(
        project_id=project_id,
        healthex_patient_id=updated.healthex_patient_id,
        status=updated.status,
        polled_at=now,
    )


@router.post(
    "/connections/{project_id}/ingest",
    response_model=HealthExIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_connection(
    project_id: str,
    uid: str = Depends(get_current_user_uid),
    repo: BaseHealthExLinksRepository = Depends(get_healthex_links_repo),
    airflow: BaseAirflowClient = Depends(get_airflow_client),
) -> HealthExIngestResponse:
    """Trigger the healthex_extract Airflow DAG for a consented patient.

    Fire-and-forget: returns 202 with `dag_run_id` immediately; the DAG
    pulls, stages the raw Bundle to S3, and ingests to OMOP. Mirrors Epic's
    manual sync endpoint at /home/nick/PycharmProjects/fhir-importers/app/routers.py:163.
    See /home/nick/PycharmProjects/healthkey-etl/healthex.md for the DAG spec.

    """
    link = await repo.get(uid, project_id)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No HealthEx link for project: {project_id}",
        )
    if link.healthex_patient_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "HealthEx has not resolved a patientId yet — consent is "
                "still pending. Wait for the status poll to advance to "
                "RETRIEVAL_IN_PROGRESS before triggering ingest."
            ),
        )

    since_iso = link.last_synced_at.isoformat() if link.last_synced_at else None
    conf = _dag_conf(
        uid=uid,
        project_id=project_id,
        external_id=link.external_id,
        healthex_patient_id=link.healthex_patient_id,
        since_iso=since_iso,
    )
    try:
        dag_run_id = await airflow.create_dag_run(
            dag=HEALTHEX_EXTRACT_DAG,
            dag_run_prefix=_dag_run_prefix(uid, project_id),
            conf=conf,
        )
    except AirflowError as exc:
        # Log the full URL/method for ops (goes to Sentry / stdout), but
        # respond with a generic message so the browser doesn't see the
        # internal Airflow URL.
        _logger.exception(
            "Failed to trigger %s DAG uid=%s project=%s",
            HEALTHEX_EXTRACT_DAG, uid, project_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Airflow trigger failed",
        ) from exc

    _logger.info(
        "healthex.ingest.triggered uid=%s project=%s patient=%s dag_run=%s sync_mode=%s",
        uid, project_id, link.healthex_patient_id, dag_run_id, conf["sync_mode"],
    )
    return HealthExIngestResponse(project_id=project_id, dag_run_id=dag_run_id)


@router.post(
    "/connections/{project_id}/reconcile",
    response_model=HealthExReconcileResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reconcile_connection(
    project_id: str,
    uid: str = Depends(get_current_user_uid),
    repo: BaseHealthExLinksRepository = Depends(get_healthex_links_repo),
    airflow: BaseAirflowClient = Depends(get_airflow_client),
) -> HealthExReconcileResponse:
    """Trigger the healthex_reconcile Airflow DAG for a single row.

    Reconciles our healthex_patient_links row against HealthEx ground truth
    (calls getPatientConsents, applies the transition table documented at
    /home/nick/PycharmProjects/healthkey-etl/healthex.md §4). Fires-and-
    forgets: returns 202 with dag_run_id; caller polls /connections until
    `last_status_polled_at` advances.

    NOT gated on `healthex_patient_id` (unlike /ingest) — reconcile is
    precisely how a PENDING_CONSENT row discovers its patient_id and moves
    to RETRIEVAL_IN_PROGRESS.
    """
    link = await repo.get(uid, project_id)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No HealthEx link for project: {project_id}",
        )

    conf = {"user_uid": uid, "project_id": project_id}
    try:
        dag_run_id = await airflow.create_dag_run(
            dag=HEALTHEX_RECONCILE_DAG,
            dag_run_prefix=_dag_run_prefix(uid, project_id),
            conf=conf,
        )
    except AirflowError as exc:
        # Full URL/method goes to Sentry via logger.exception; response body
        # stays generic so the internal Airflow URL doesn't leak (same as /ingest).
        _logger.exception(
            "Failed to trigger %s DAG uid=%s project=%s",
            HEALTHEX_RECONCILE_DAG, uid, project_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Airflow trigger failed",
        ) from exc

    _logger.info(
        "healthex.reconcile.triggered uid=%s project=%s dag_run=%s",
        uid, project_id, dag_run_id,
    )
    return HealthExReconcileResponse(project_id=project_id, dag_run_id=dag_run_id)


def _to_response(meta) -> HealthExLinkResponse:
    return HealthExLinkResponse(
        project_id=meta.project_id,
        external_id=meta.external_id,
        healthex_patient_id=meta.healthex_patient_id,
        status=meta.status,
        onboarding_url=meta.onboarding_url,
        consented_at=meta.consented_at,
        last_status_polled_at=meta.last_status_polled_at,
        last_synced_at=meta.last_synced_at,
        connected_at=meta.connected_at,
    )
