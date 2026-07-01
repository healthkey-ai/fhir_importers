from datetime import datetime

from pydantic import BaseModel, Field


class Connection(BaseModel):
    organization_alias: str
    patient: str | None = None
    scope: str | None = None
    expires_at: datetime
    connected_at: datetime
    last_synced_at: datetime | None = None


class Organization(BaseModel):
    alias: str
    title: str
    endpoint_url: str


class StartOAuthRequest(BaseModel):
    organization_alias: str = Field(..., description="Alias of an organization registered in organizations.json")


class StartOAuthResponse(BaseModel):
    authorization_url: str
    state: str


class FinishOAuthRequest(BaseModel):
    code: str
    state: str


class FinishOAuthResponse(BaseModel):
    organization_alias: str
    patient: str | None = Field(None, description="SMART-on-FHIR patient launch context, if returned")
    scope: str | None = None
    status: str
    connected_at: datetime


class SyncConnectionResponse(BaseModel):
    organization_alias: str
    dag_run_id: str


class HealthExConnectRequest(BaseModel):
    email: str = Field(..., description="User's email — required by HealthEx addPatients")
    first_name: str | None = None
    last_name: str | None = None


class HealthExLinkResponse(BaseModel):
    project_id: str
    external_id: str
    healthex_patient_id: str | None = None
    status: str
    onboarding_url: str | None = None
    consented_at: datetime | None = None
    last_status_polled_at: datetime | None = None
    last_synced_at: datetime | None = None
    connected_at: datetime


class HealthExStatusResponse(BaseModel):
    project_id: str
    healthex_patient_id: str | None
    status: str
    overall_status: str | None = None
    vectorization_status: str | None = None
    polled_at: datetime | None = None


class HealthExRefreshResponse(BaseModel):
    """Summary of a manual `POST .../refresh` pull.

    Deliberately compact — the frontend only needs to display "we pulled
    N resources of M types in T seconds". Per-page breakdowns and the raw
    Bundle stay in the backend logs (see healthex_client.pull_everything).
    """
    project_id: str
    healthex_patient_id: str
    total_entries: int
    pages: int
    duration_ms: int
    resource_type_counts: dict[str, int]
    truncated: bool
    synced_at: datetime
