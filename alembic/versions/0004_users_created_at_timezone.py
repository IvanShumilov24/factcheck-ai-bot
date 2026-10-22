"""Use timezone-aware UTC timestamps for users."""
from alembic import op
import sqlalchemy as sa


revision = "0004_users_created_at_timezone"
down_revision = "0003_evidence_quality_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
