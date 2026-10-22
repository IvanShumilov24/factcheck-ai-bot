"""Persist whether evidence analysis failed instead of returning a normal result."""

from alembic import op
import sqlalchemy as sa


revision = "0006_analysis_failure_flag"
down_revision = "0005_production_job_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("category", sa.String(length=40), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column(
        "evidence_analyses",
        sa.Column("analysis_failed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("evidence_analyses", "analysis_failed")
    op.drop_column("claims", "category")
