from pydantic import BaseModel, Field


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
    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None
    expires_in: int
    scope: str | None = None
    patient: str | None = Field(None, description="SMART-on-FHIR patient launch context, if returned")
