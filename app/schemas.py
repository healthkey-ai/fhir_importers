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


class HealthExIngestResponse(BaseModel):
    """Response for POST .../ingest — triggers healthex_extract Airflow DAG.

    Fires-and-forgets; the caller polls Airflow (or a future callback) for
    completion. Mirrors SyncConnectionResponse for the Epic path.
    """
    project_id: str
    dag_run_id: str


class HealthExReconcileResponse(BaseModel):
    """Response for POST .../reconcile — triggers healthex_reconcile DAG.

    `debounced` is True when the backend suppressed the DAG trigger because
    the row was reconciled (or otherwise polled) recently — `dag_run_id`
    is None in that case. Callers treat both branches identically: refetch
    /connections after a short delay to see the row state.
    """
    project_id: str
    dag_run_id: str | None = None
    debounced: bool = False


