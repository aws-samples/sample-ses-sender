"""add_sending_jobs_table

Revision ID: dd865c786550
Revises: 84a14f45b6bb
Create Date: 2026-02-07 05:25:43.445716

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd865c786550'
down_revision: Union[str, Sequence[str], None] = '84a14f45b6bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('sending_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('batch_id', sa.String(length=64), nullable=True),
        sa.Column('template_name', sa.String(length=255), nullable=True),
        sa.Column('group_name', sa.String(length=255), nullable=True),
        sa.Column('source_email', sa.String(length=255), nullable=True),
        sa.Column('total_contacts', sa.Integer(), nullable=True),
        sa.Column('total_batches', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('configuration_set', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sending_jobs_id'), 'sending_jobs', ['id'], unique=False)
    op.create_index(op.f('ix_sending_jobs_user_id'), 'sending_jobs', ['user_id'], unique=False)
    op.create_index('ix_sending_jobs_batch_id', 'sending_jobs', ['batch_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_sending_jobs_batch_id', table_name='sending_jobs')
    op.drop_index(op.f('ix_sending_jobs_user_id'), table_name='sending_jobs')
    op.drop_index(op.f('ix_sending_jobs_id'), table_name='sending_jobs')
    op.drop_table('sending_jobs')
