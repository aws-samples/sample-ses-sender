"""add template_id to sending_jobs

Revision ID: f6a7b8c9d016
Revises: e5f6a7b8c905
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c9d016"
down_revision = "e5f6a7b8c905"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sending_jobs", sa.Column("template_id", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("sending_jobs", "template_id")
