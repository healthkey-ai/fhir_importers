from datetime import datetime

from sqlalchemy import Column, DateTime, UniqueConstraint
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
