"""add_contact_email_to_users

Revision ID: c3d4e5f6a703
Revises: b2c3d4e5f602
Create Date: 2026-05-09 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a703"
down_revision = "b2c3d4e5f602"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("contact_email", sa.String(255), nullable=True))
    # 默认值设为发件邮箱
    op.execute("UPDATE users SET contact_email = email WHERE contact_email IS NULL")


def downgrade():
    op.drop_column("users", "contact_email")
