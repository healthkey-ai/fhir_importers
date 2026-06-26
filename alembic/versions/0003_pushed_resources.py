from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_pushed_resources"
down_revision: Union[str, None] = "0002_last_synced_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pushed_resources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("fhir_resource_type", sa.String(), nullable=False),
        sa.Column("fhir_resource_id", sa.String(), nullable=False),
        sa.Column("ctomop_endpoint", sa.String(), nullable=False),
        sa.Column("ctomop_row_id", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["mychart_connections.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "connection_id",
            "fhir_resource_type",
            "fhir_resource_id",
            name="uq_pushed_resources_conn_resource",
        ),
    )
    op.create_index(
        "ix_pushed_resources_connection_id",
        "pushed_resources",
        ["connection_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pushed_resources_connection_id", table_name="pushed_resources")
    op.drop_table("pushed_resources")
