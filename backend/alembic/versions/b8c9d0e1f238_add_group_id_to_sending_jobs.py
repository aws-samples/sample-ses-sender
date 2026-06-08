"""add group_id to sending_jobs

Revision ID: b8c9d0e1f238
Revises: a7b8c9d0e127
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = "b8c9d0e1f238"
down_revision = "a7b8c9d0e127"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sending_jobs", sa.Column("group_id", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("sending_jobs", "group_id")
