"""add_daily_send_limit_to_users

Revision ID: e8f5a6b9c012
Revises: d7e4f5a8b901
Create Date: 2026-04-10 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "e8f5a6b9c012"
down_revision = "d7e4f5a8b901"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("daily_send_limit", sa.Integer(), nullable=True, server_default="1000"))


def downgrade():
    op.drop_column("users", "daily_send_limit")
