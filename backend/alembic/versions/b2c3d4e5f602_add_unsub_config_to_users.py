"""add_unsub_config_to_users

Revision ID: b2c3d4e5f602
Revises: a1b2c3d4e501
Create Date: 2026-04-24 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f602"
down_revision = "a1b2c3d4e501"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("unsub_config", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("users", "unsub_config")
