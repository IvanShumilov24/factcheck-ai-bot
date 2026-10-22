"""Persist source access and evidence quality metadata."""
from alembic import op
import sqlalchemy as sa


revision = "0003_evidence_quality_fields"
down_revision = "0002_fact_check_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("content_status", sa.String(32), nullable=False, server_default="NOT_FETCHED"),
    )
    op.add_column("sources", sa.Column("fetch_error", sa.Text(), nullable=True))
    op.add_column(
        "evidence",
        sa.Column("directness", sa.String(32), nullable=False, server_default="DIRECT"),
    )
    op.add_column(
        "evidence",
        sa.Column("scope", sa.String(64), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column(
        "evidence",
        sa.Column("usable", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("sources", "content_status", server_default=None)
    op.alter_column("evidence", "directness", server_default=None)
    op.alter_column("evidence", "scope", server_default=None)
    op.alter_column("evidence", "usable", server_default=None)


def downgrade() -> None:
    op.drop_column("evidence", "usable")
    op.drop_column("evidence", "scope")
    op.drop_column("evidence", "directness")
    op.drop_column("sources", "fetch_error")
    op.drop_column("sources", "content_status")
