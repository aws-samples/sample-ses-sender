"""add email_blacklist table

Revision ID: e5f6a7b8c905
Revises: d4e5f6a7b804
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c905"
down_revision = "d4e5f6a7b804"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_blacklist",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("reason", sa.String(500), server_default=""),
        sa.Column("created_by", sa.String(100), server_default="admin"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("email_blacklist")
