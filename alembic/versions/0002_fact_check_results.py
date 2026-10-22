"""Persist complete fact-check results."""
from alembic import op
import sqlalchemy as sa


revision = "0002_fact_check_results"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_type", sa.String(32), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pipeline_version", sa.String(32), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
    )
    op.create_index("ix_checks_user_id", "checks", ["user_id"])
    op.create_index("ix_checks_created_at", "checks", ["created_at"])
    op.create_index("ix_checks_input_hash", "checks", ["input_hash"])

    op.create_table(
        "claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("check_id", sa.Integer(), sa.ForeignKey("checks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_key", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(32), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("claim_order", sa.Integer(), nullable=False),
    )
    op.create_index("ix_claims_check_id", "claims", ["check_id"])

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_id", sa.Integer(), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("authority_level", sa.String(32), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sources_claim_id", "sources", ["claim_id"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_id", sa.Integer(), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("relation", sa.String(32), nullable=False),
        sa.Column("evidence_strength", sa.String(32), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
    )
    op.create_index("ix_evidence_claim_id", "evidence", ["claim_id"])
    op.create_index("ix_evidence_source_id", "evidence", ["source_id"])

    op.create_table(
        "evidence_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_id", sa.Integer(), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("overall_evidence_strength", sa.String(32), nullable=False),
        sa.Column("evidence_consistency", sa.String(32), nullable=False),
        sa.Column("conflict_detected", sa.Boolean(), nullable=False),
        sa.Column("supporting_evidence", sa.JSON(), nullable=False),
        sa.Column("contradicting_evidence", sa.JSON(), nullable=False),
        sa.Column("neutral_evidence", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "verdicts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_id", sa.Integer(), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("short_reason", sa.Text(), nullable=False),
        sa.Column("detailed_reason", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("verdicts")
    op.drop_table("evidence_analyses")
    op.drop_table("evidence")
    op.drop_table("sources")
    op.drop_table("claims")
    op.drop_table("checks")
