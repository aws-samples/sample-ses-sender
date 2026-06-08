"""add_unsubscribe_list_table

Revision ID: c6d3e4f7b890
Revises: b5d2e3f6a789
Create Date: 2026-01-30 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6d3e4f7b890'
down_revision: Union[str, None] = 'b5d2e3f6a789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'unsubscribe_list',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email', sa.String(255), nullable=False, index=True),
        sa.Column('source_email', sa.String(255), nullable=False, index=True),
        sa.Column('reason', sa.String(32), nullable=True, server_default='one-click'),
        sa.Column('unsubscribed_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_unsub_email_source', 'unsubscribe_list', ['email', 'source_email'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_unsub_email_source', table_name='unsubscribe_list')
    op.drop_table('unsubscribe_list')
