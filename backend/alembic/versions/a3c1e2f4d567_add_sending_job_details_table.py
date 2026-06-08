"""add_sending_job_details_table

Revision ID: a3c1e2f4d567
Revises: dd865c786550
Create Date: 2026-02-12 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c1e2f4d567'
down_revision: Union[str, None] = 'dd865c786550'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sending_job_details',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('job_id', sa.Integer(), nullable=True, index=True),
        sa.Column('batch_id', sa.String(64), nullable=True, index=True),
        sa.Column('message_id', sa.String(128), nullable=True, index=True),
        sa.Column('recipient', sa.String(256), nullable=True, index=True),
        sa.Column('send_status', sa.String(32), nullable=True, server_default='Pending'),
        sa.Column('send_error', sa.Text(), nullable=True),
        sa.Column('delivery_status', sa.String(32), nullable=True),
        sa.Column('delivery_time', sa.DateTime(), nullable=True),
        sa.Column('bounce_type', sa.String(64), nullable=True),
        sa.Column('bounce_subtype', sa.String(64), nullable=True),
        sa.Column('bounce_message', sa.Text(), nullable=True),
        sa.Column('open_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('first_open_time', sa.DateTime(), nullable=True),
        sa.Column('click_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('first_click_time', sa.DateTime(), nullable=True),
        sa.Column('complaint_time', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('sending_job_details')
