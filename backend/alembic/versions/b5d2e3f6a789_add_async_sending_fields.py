"""add_async_sending_fields

Revision ID: b5d2e3f6a789
Revises: a3c1e2f4d567
Create Date: 2026-01-30 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d2e3f6a789'
down_revision: Union[str, None] = 'a3c1e2f4d567'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sending_jobs 表添加异步发送相关字段
    op.add_column('sending_jobs', sa.Column('sent_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('sending_jobs', sa.Column('finished_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('sending_jobs', 'finished_at')
    op.drop_column('sending_jobs', 'sent_count')
