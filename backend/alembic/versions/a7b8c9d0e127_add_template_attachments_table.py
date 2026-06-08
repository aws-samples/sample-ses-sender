"""add template_attachments table

Revision ID: a7b8c9d0e127
Revises: f6a7b8c9d016
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e127"
down_revision = "f6a7b8c9d016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "template_attachments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer(), nullable=False, index=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("file_size", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("template_attachments")
