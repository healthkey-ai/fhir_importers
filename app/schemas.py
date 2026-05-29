from datetime import datetime

from pydantic import BaseModel, Field


class ConnectionOut(BaseModel):
    organization_alias: str
    patient: str | None = None
    scope: str | None = None
    expires_at: datetime
    connected_at: datetime


class OrganizationOut(BaseModel):
    alias: str
    title: str
    endpoint_url: str


class StartRequest(BaseModel):
    organization_alias: str = Field(..., description="Alias of an organization registered in organizations.json")


class StartResponse(BaseModel):
    authorization_url: str
    state: str


class FinishRequest(BaseModel):
    code: str
    state: str


class FinishResponse(BaseModel):
    organization_alias: str
    patient: str | None = Field(None, description="SMART-on-FHIR patient launch context, if returned")
    scope: str | None = None
    status: str
    connected_at: datetime


class SyncResponse(BaseModel):
    organization_alias: str
    dag_run_id: str
