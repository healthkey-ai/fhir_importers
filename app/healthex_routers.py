import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .auth import get_current_user_uid
from services.healthex_client import BaseHealthExClient, HealthExError
from .healthex_links import (
    STATUS_COMPLETE,
    STATUS_ERROR,
    STATUS_PENDING_CONSENT,
    STATUS_RETRIEVAL_IN_PROGRESS,
    BaseHealthExLinksRepository,
    HealthExLinksRepository,
)
from .schemas import (
    HealthExLinkResponse,
    HealthExStatusResponse,
)


_logger = logging.getLogger(__name__)


def get_healthex_client(request: Request) -> BaseHealthExClient:
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
    uid: str = Depends(get_current_user_uid),
    repo: BaseHealthExLinksRepository = Depends(get_healthex_links_repo),
    client: BaseHealthExClient = Depends(get_healthex_client),
    project_id: str = Depends(get_healthex_project_id),
) -> HealthExLinkResponse:
    # Idempotent: re-issuing the link mints a fresh signature each call, so
    # serve the persisted one if we already have a link for this user/project.
    if existing := await repo.get(uid, project_id):
        return _to_response(existing)

    try:
        onboarding_url = await client.get_unique_link(
            project_id=project_id, external_id=uid,
        )
    except HealthExError as exc:
        _logger.exception("HealthEx get_unique_link failed for uid=%s", uid)
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
    client: BaseHealthExClient = Depends(get_healthex_client),
) -> HealthExStatusResponse:
    link = await repo.get(uid, project_id)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No HealthEx link for project: {project_id}",
        )

    now = datetime.now(timezone.utc)

    # Phase 1: resolve patientId by externalId. Until the patient consents on
    # HealthEx, this returns None — the row stays PENDING_CONSENT.
    if link.healthex_patient_id is None:
        try:
            patient_id = await client.find_patient_id_by_external_id(
                project_id=project_id, external_id=link.external_id,
            )
        except HealthExError as exc:
            _logger.exception("HealthEx lookup failed uid=%s", uid)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"HealthEx upstream error: {exc}",
            ) from exc
        if patient_id is None:
            updated = await repo.update_status(
                user_uid=uid, project_id=project_id,
                status=STATUS_PENDING_CONSENT, polled_at=now,
            )
            assert updated is not None
            return HealthExStatusResponse(
                project_id=project_id, healthex_patient_id=None,
                status=updated.status, polled_at=now,
            )
        link = await repo.update_status(
            user_uid=uid, project_id=project_id,
            status=STATUS_RETRIEVAL_IN_PROGRESS,
            healthex_patient_id=patient_id, polled_at=now, consented_at=now,
        )
        assert link is not None

    # Phase 2: patient is consented — poll the data-retrieval pipeline.
    try:
        upstream = await client.get_data_retrieval_status(
            project_id=project_id, patient_id=link.healthex_patient_id,
        )
    except HealthExError as exc:
        _logger.exception(
            "HealthEx status poll failed uid=%s patient=%s",
            uid, link.healthex_patient_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"HealthEx upstream error: {exc}",
        ) from exc

    new_status = _map_upstream_status(upstream.overall_status, link.status)
    updated = await repo.update_status(
        user_uid=uid, project_id=project_id,
        status=new_status, polled_at=now,
    )
    assert updated is not None
    return HealthExStatusResponse(
        project_id=project_id,
        healthex_patient_id=updated.healthex_patient_id,
        status=updated.status,
        overall_status=upstream.overall_status,
        vectorization_status=upstream.vectorization_status,
        polled_at=now,
    )


def _map_upstream_status(upstream: str, current: str) -> str:
    """Coerce HealthEx's `dataRetrievalStatus` to our state machine.

    HealthEx reports COMPLETE / IN_PROGRESS / NOT_STARTED / ERROR per their
    docs; the exact string set is unverified — anything we don't recognize is
    a no-op (keeps the current status) to avoid corrupting state on a doc lag.
    """
    upstream_norm = (upstream or "").upper()
    if upstream_norm in {"COMPLETE", "COMPLETED"}:
        return STATUS_COMPLETE
    if upstream_norm in {"IN_PROGRESS", "RUNNING"}:
        return STATUS_RETRIEVAL_IN_PROGRESS
    if upstream_norm == "ERROR":
        return STATUS_ERROR
    if upstream_norm in {"NOT_STARTED", "PENDING"}:
        # Still awaiting consent / retrieval kickoff upstream.
        return current
    return current


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
