from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_healthex_patient_links"
down_revision: Union[str, None] = "0003_pushed_resources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "healthex_patient_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_uid", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("healthex_patient_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("onboarding_url", sa.String(), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_uid", "project_id", name="uq_healthex_user_project",
        ),
    )
    op.create_index(
        "ix_healthex_patient_links_user_uid",
        "healthex_patient_links",
        ["user_uid"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_healthex_patient_links_user_uid",
        table_name="healthex_patient_links",
    )
    op.drop_table("healthex_patient_links")
