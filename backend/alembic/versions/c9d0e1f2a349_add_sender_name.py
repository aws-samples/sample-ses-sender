"""add sender_name to users and sending_jobs

Revision ID: c9d0e1f2a349
Revises: b8c9d0e1f238
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a349"
down_revision = "b8c9d0e1f238"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("sender_name", sa.String(255), nullable=True))
    op.add_column("sending_jobs", sa.Column("sender_name", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("sending_jobs", "sender_name")
    op.drop_column("users", "sender_name")
