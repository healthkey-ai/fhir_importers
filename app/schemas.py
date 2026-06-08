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
