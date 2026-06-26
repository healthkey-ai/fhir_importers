from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlmodel import Field, SQLModel


def _tz_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)


class MyChartConnection(SQLModel, table=True):
    __tablename__ = "mychart_connections"
    __table_args__ = (
        UniqueConstraint("user_uid", "organization_alias", name="uq_user_org"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_uid: str = Field(index=True)
    organization_alias: str

    # Epic tokens — stored Fernet-encrypted (see crypto.TokenCipher).
    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None

    scope: str | None = None
    patient: str | None = None
    expires_at: datetime = Field(sa_column=_tz_column())
    created_at: datetime = Field(sa_column=_tz_column())
    updated_at: datetime = Field(sa_column=_tz_column())
    # Written by Airflow's fhir_extract DAG after each successful sync.
    last_synced_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class HealthExLink(SQLModel, table=True):
    """One user's onboarding into a HealthEx Project.

    HealthEx is org-scoped (no per-user tokens); this row only records the
    `(user_uid, project_id)` mapping, the HealthEx-assigned `patient_id` once
    issued, and the async retrieval status we poll until COMPLETE.
    """

    __tablename__ = "healthex_patient_links"
    __table_args__ = (
        UniqueConstraint("user_uid", "project_id", name="uq_healthex_user_project"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_uid: str = Field(index=True)
    project_id: str
    # external_id is what we send HealthEx as our patient identifier; today =
    # user_uid, but kept as a separate column in case those diverge later.
    external_id: str
    healthex_patient_id: str | None = None
    status: str  # PENDING_CONSENT | RETRIEVAL_IN_PROGRESS | COMPLETE | ERROR | REVOKED
    onboarding_url: str | None = None
    consented_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_status_polled_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_synced_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(sa_column=_tz_column())
    updated_at: datetime = Field(sa_column=_tz_column())


class PushedResource(SQLModel, table=True):
    """Idempotency ledger of FHIR resources pushed to ctomop, per connection.

    MVP workaround — see healthkey-etl/docs/ctomop-integration.md → Idempotency.
    """

    __tablename__ = "pushed_resources"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "fhir_resource_type",
            "fhir_resource_id",
            name="uq_pushed_resources_conn_resource",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    connection_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("mychart_connections.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    fhir_resource_type: str
    fhir_resource_id: str
    ctomop_endpoint: str
    ctomop_row_id: int
    content_hash: str  # recorded for future PATCH support; not enforced in MVP
    pushed_at: datetime = Field(sa_column=_tz_column())
