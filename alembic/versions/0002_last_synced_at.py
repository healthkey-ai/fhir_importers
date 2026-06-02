"""add last_synced_at column

Revision ID: 0002_last_synced_at
Revises: 0001_initial
Create Date: 2026-06-02

Written by Airflow's fhir_extract DAG after each successful sync; read by
main's /epic/connections endpoint for the UI's "Last synced X hours ago".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_last_synced_at"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mychart_connections",
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mychart_connections", "last_synced_at")
