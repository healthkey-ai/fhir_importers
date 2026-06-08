import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .airflow import BaseAirflowClient
from .auth import get_current_user_uid
from .connections import BaseConnectionsRepository, ConnectionsRepository
from .organizations import OrganizationRegistry, UnknownOrganization
from .schemas import (
    Connection,
    FinishOAuthRequest,
    FinishOAuthResponse,
    Organization,
    StartOAuthRequest,
    StartOAuthResponse,
    SyncConnectionResponse,
)
from .service import EpicAuthService, InvalidStateError


_logger = logging.getLogger(__name__)

FHIR_EXTRACT_DAG = "fhir_extract"


def get_epic_auth_service(request: Request) -> EpicAuthService:
    return request.app.state.epic_auth_service


def get_organizations(request: Request) -> OrganizationRegistry:
    return request.app.state.organizations


def get_airflow_client(request: Request) -> BaseAirflowClient:
    return request.app.state.airflow_client


def _dag_run_prefix(uid: str, organization_alias: str) -> str:
    return f"{uid}__{organization_alias}"


def _dag_conf(uid: str, organization_alias: str, epic_patient_id: str | None) -> dict:
    return {
        "user_uid": uid,
        "organization_alias": organization_alias,
        "epic_patient_id": epic_patient_id,
    }


async def get_connections_repo(request: Request) -> AsyncIterator[BaseConnectionsRepository]:
    sessionmaker = request.app.state.db_sessionmaker
    async with sessionmaker() as session:
        yield ConnectionsRepository(session, request.app.state.token_cipher)


router = APIRouter(prefix="/epic", tags=["epic-auth"])


@router.get("/connections", response_model=list[Connection])
async def list_connections(
    uid: str = Depends(get_current_user_uid),
    repo: BaseConnectionsRepository = Depends(get_connections_repo),
) -> list[Connection]:
    items = await repo.list_for_user(uid)
    return [
        Connection(
            organization_alias=i.organization_alias,
            patient=i.patient,
            scope=i.scope,
            expires_at=i.expires_at,
            connected_at=i.connected_at,
            last_synced_at=i.last_synced_at,
        )
        for i in items
    ]


@router.get("/organizations", response_model=list[Organization])
async def list_organizations(
    organizations: OrganizationRegistry = Depends(get_organizations),
) -> list[Organization]:
    return [
        Organization(alias=o.alias, title=o.title, endpoint_url=o.endpoint_url)
        for o in organizations.list()
    ]


@router.delete("/connections/{organization_alias}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    organization_alias: str,
    uid: str = Depends(get_current_user_uid),
    repo: BaseConnectionsRepository = Depends(get_connections_repo),
) -> Response:
    deleted = await repo.delete(uid, organization_alias)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No connection for organization: {organization_alias}",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/start", response_model=StartOAuthResponse)
async def start(
    body: StartOAuthRequest,
    service: EpicAuthService = Depends(get_epic_auth_service),
) -> StartOAuthResponse:
    try:
        result = await service.start(body.organization_alias)
    except UnknownOrganization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown organization alias: {body.organization_alias}",
        )
    return StartOAuthResponse(authorization_url=result.authorization_url, state=result.state)


@router.post("/auth/finish", response_model=FinishOAuthResponse)
async def finish(
    body: FinishOAuthRequest,
    uid: str = Depends(get_current_user_uid),
    repo: BaseConnectionsRepository = Depends(get_connections_repo),
    service: EpicAuthService = Depends(get_epic_auth_service),
    airflow: BaseAirflowClient = Depends(get_airflow_client),
) -> FinishOAuthResponse:
    try:
        result = await service.finish(body.code, body.state)
    except InvalidStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    conn = await repo.upsert(
        user_uid=uid,
        organization_alias=result.organization_alias,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        id_token=result.id_token,
        scope=result.scope,
        patient=result.patient,
        expires_at=result.expires_at,
    )

    # Best-effort: connection is saved regardless. /sync is available for retries.
    try:
        dag_run_id = await airflow.create_dag_run(
            dag=FHIR_EXTRACT_DAG,
            dag_run_prefix=_dag_run_prefix(uid, conn.organization_alias),
            conf=_dag_conf(uid, conn.organization_alias, conn.patient),
        )
        _logger.info("Triggered %s DAG run=%s", FHIR_EXTRACT_DAG, dag_run_id)
    except Exception:
        _logger.exception("Failed to trigger %s DAG (connection persisted)", FHIR_EXTRACT_DAG)

    return FinishOAuthResponse(
        organization_alias=conn.organization_alias,
        patient=conn.patient,
        scope=conn.scope,
        status="connected",
        connected_at=conn.connected_at,
    )


@router.post("/connections/{organization_alias}/sync", response_model=SyncConnectionResponse, status_code=status.HTTP_202_ACCEPTED)
async def sync_connection(
    organization_alias: str,
    uid: str = Depends(get_current_user_uid),
    repo: BaseConnectionsRepository = Depends(get_connections_repo),
    airflow: BaseAirflowClient = Depends(get_airflow_client),
) -> SyncConnectionResponse:
    items = await repo.list_for_user(uid)
    conn = next((c for c in items if c.organization_alias == organization_alias), None)
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No connection for organization: {organization_alias}",
        )

    dag_run_id = await airflow.create_dag_run(
        dag=FHIR_EXTRACT_DAG,
        dag_run_prefix=_dag_run_prefix(uid, organization_alias),
        conf=_dag_conf(uid, organization_alias, conn.patient),
    )
    return SyncConnectionResponse(organization_alias=organization_alias, dag_run_id=dag_run_id)
