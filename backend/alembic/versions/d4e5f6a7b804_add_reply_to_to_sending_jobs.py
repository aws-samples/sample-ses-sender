"""add_reply_to_to_sending_jobs

Revision ID: d4e5f6a7b804
Revises: c3d4e5f6a703
Create Date: 2026-05-09 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b804"
down_revision = "c3d4e5f6a703"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sending_jobs", sa.Column("reply_to", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("sending_jobs", "reply_to")
