import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .auth import get_current_user_uid
from services.healthex_client import HealthExClient, HealthExError
from .healthex_links import (
    STATUS_COMPLETE,
    STATUS_ERROR,
    STATUS_PENDING_CONSENT,
    STATUS_RETRIEVAL_IN_PROGRESS,
    BaseHealthExLinksRepository,
    HealthExLinksRepository,
)
from .schemas import (
    HealthExConnectRequest,
    HealthExLinkResponse,
    HealthExRefreshResponse,
    HealthExStatusResponse,
)


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
    client: HealthExClient = Depends(get_healthex_client),
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
                link.external_id,
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
            if updated is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="HealthEx link mutated mid-poll",
                )
            return HealthExStatusResponse(
                project_id=project_id, healthex_patient_id=None,
                status=updated.status, polled_at=now,
            )
        link = await repo.update_status(
            user_uid=uid, project_id=project_id,
            status=STATUS_RETRIEVAL_IN_PROGRESS,
            healthex_patient_id=patient_id, polled_at=now, consented_at=now,
        )
        if link is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="HealthEx link mutated mid-poll",
            )

    # Phase 2: patient is consented — poll the data-retrieval pipeline.
    try:
        upstream = await client.get_data_retrieval_status(
            link.healthex_patient_id,
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

    # `upstream is None` means HealthEx doesn't expose an org-scoped status
    # endpoint (see HealthExClient.get_data_retrieval_status). Keep the row's
    # current status and just refresh polled_at so the UI stops looking like
    # the backend is stuck.
    new_status = (
        _map_upstream_status(upstream.overall_status, link.status)
        if upstream is not None else link.status
    )
    updated = await repo.update_status(
        user_uid=uid, project_id=project_id,
        status=new_status, polled_at=now,
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
        overall_status=upstream.overall_status if upstream is not None else None,
        vectorization_status=(
            upstream.vectorization_status if upstream is not None else None
        ),
        polled_at=now,
    )


@router.post(
    "/connections/{project_id}/refresh",
    response_model=HealthExRefreshResponse,
)
async def refresh_connection(
    project_id: str,
    uid: str = Depends(get_current_user_uid),
    repo: BaseHealthExLinksRepository = Depends(get_healthex_links_repo),
    client: HealthExClient = Depends(get_healthex_client),
) -> HealthExRefreshResponse:
    """Manually pull the patient's FHIR bundle from HealthEx.

    In-process for now — no Airflow DAG involved. Once the healthkey-etl
    HealthEx extract DAG exists (see /home/nick/PycharmProjects/healthkey-etl/healthex.md),
    this endpoint will trigger it instead and return `dag_run_id` for the
    UI to poll. Right now the goal is experimental: verify we can pull,
    learn `$everything` semantics from the logs (page count, resource
    breakdown, timing), and give the operator a manual "kick" button.

    Response is a compact summary; full per-page and per-resource-type
    breakdowns are in the backend logs (search for
    `healthex.pull_everything.*`).
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
                "RETRIEVAL_IN_PROGRESS before refreshing."
            ),
        )

    # Pass `since=last_synced_at` so subsequent refreshes only ask HealthEx
    # for records touched after the last successful pull. HealthEx's own
    # docs note `_since` is best-effort (not guaranteed minimal delta), so
    # the caller-side dedup ledger — TODO — must still run before OMOP
    # ingestion. For now (no ingestion), an occasional re-fetch is harmless.
    since_iso = link.last_synced_at.isoformat() if link.last_synced_at else None

    try:
        bundle = await client.pull_everything(
            link.healthex_patient_id, since=since_iso,
        )
    except HealthExError as exc:
        _logger.exception(
            "HealthEx refresh failed uid=%s patient=%s",
            uid, link.healthex_patient_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"HealthEx upstream error: {exc}",
        ) from exc

    entries = bundle.get("entry") or []
    type_counts: dict[str, int] = {}
    for e in entries:
        rt = ((e or {}).get("resource") or {}).get("resourceType", "?")
        type_counts[rt] = type_counts.get(rt, 0) + 1
    stats = bundle.get("_healthkey_pull_stats") or {}

    now = datetime.now(timezone.utc)
    # Even the first successful pull leaves the row in RETRIEVAL_IN_PROGRESS
    # rather than COMPLETE: we don't yet ingest to OMOP, and marking
    # COMPLETE would mislead future callers. Update last_synced_at so the
    # next refresh uses it as `_since`, but keep status the same.
    await repo.update_status(
        user_uid=uid, project_id=project_id,
        status=link.status, synced_at=now,
    )

    _logger.info(
        "healthex.refresh.done uid=%s patient=%s entries=%s types=%s "
        "pages=%s duration_ms=%s since=%s",
        uid, link.healthex_patient_id, len(entries), type_counts,
        stats.get("pages"), stats.get("duration_ms"), since_iso or "-",
    )
    return HealthExRefreshResponse(
        project_id=project_id,
        healthex_patient_id=link.healthex_patient_id,
        total_entries=len(entries),
        pages=int(stats.get("pages", 1)),
        duration_ms=int(stats.get("duration_ms", 0)),
        resource_type_counts=type_counts,
        truncated=bool(stats.get("truncated", False)),
        synced_at=now,
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
