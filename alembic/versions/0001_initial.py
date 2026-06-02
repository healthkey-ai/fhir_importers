"""initial mychart_connections table

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-02

On existing deploys: `alembic stamp 0001_initial` to mark the table as
already-present (it was previously created by SQLModel.metadata.create_all).
On fresh deploys: `alembic upgrade head` creates it from this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mychart_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_uid", sa.String(), nullable=False),
        sa.Column("organization_alias", sa.String(), nullable=False),
        sa.Column("access_token", sa.String(), nullable=False),
        sa.Column("refresh_token", sa.String(), nullable=True),
        sa.Column("id_token", sa.String(), nullable=True),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("patient", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_uid", "organization_alias", name="uq_user_org"),
    )
    op.create_index(
        "ix_mychart_connections_user_uid",
        "mychart_connections",
        ["user_uid"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mychart_connections_user_uid", table_name="mychart_connections")
    op.drop_table("mychart_connections")
