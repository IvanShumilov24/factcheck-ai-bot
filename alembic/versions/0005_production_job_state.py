"""Add durable background job state to checks."""
from alembic import op
import sqlalchemy as sa


revision = "0005_production_job_state"
down_revision = "0004_users_created_at_timezone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("checks", sa.Column("job_payload", sa.JSON(), nullable=True))
    op.add_column("checks", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("checks", sa.Column("last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("checks", "last_error")
    op.drop_column("checks", "attempt_count")
    op.drop_column("checks", "job_payload")
