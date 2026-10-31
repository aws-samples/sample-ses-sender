"""add regional SES suppression snapshots and sync state

Revision ID: d0e1f2a3b450
Revises: c9d0e1f2a349
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa

revision = "d0e1f2a3b450"
down_revision = "c9d0e1f2a349"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ses_suppressed_destinations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("last_update_time", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("region", "email", name="uq_ses_suppressed_region_email"),
    )
    op.create_table(
        "ses_suppression_sync_state",
        sa.Column("region", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_table("ses_suppression_sync_state")
    op.drop_table("ses_suppressed_destinations")
