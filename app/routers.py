from fastapi import APIRouter, Depends, HTTPException, Request, status

from .organizations import OrganizationRegistry, UnknownOrganization
from .schemas import (
    FinishRequest,
    FinishResponse,
    OrganizationOut,
    StartRequest,
    StartResponse,
)
from .service import EpicAuthService, InvalidStateError


def get_epic_auth_service(request: Request) -> EpicAuthService:
    return request.app.state.epic_auth_service


def get_organizations(request: Request) -> OrganizationRegistry:
    return request.app.state.organizations


router = APIRouter(prefix="/epic", tags=["epic-auth"])


@router.get("/organizations", response_model=list[OrganizationOut])
async def list_organizations(
    organizations: OrganizationRegistry = Depends(get_organizations),
) -> list[OrganizationOut]:
    return [
        OrganizationOut(alias=o.alias, title=o.title, endpoint_url=o.endpoint_url)
        for o in organizations.list()
    ]


@router.post("/auth/start", response_model=StartResponse)
async def start(
    body: StartRequest,
    service: EpicAuthService = Depends(get_epic_auth_service),
) -> StartResponse:
    try:
        result = await service.start(body.organization_alias)
    except UnknownOrganization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown organization alias: {body.organization_alias}",
        )
    return StartResponse(authorization_url=result.authorization_url, state=result.state)


@router.post("/auth/finish", response_model=FinishResponse)
async def finish(
    body: FinishRequest,
    service: EpicAuthService = Depends(get_epic_auth_service),
) -> FinishResponse:
    try:
        tokens = await service.finish(body.code, body.state)
    except InvalidStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return FinishResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        id_token=tokens.id_token,
        expires_in=tokens.expires_in,
        scope=tokens.scope,
        patient=tokens.patient,
    )
