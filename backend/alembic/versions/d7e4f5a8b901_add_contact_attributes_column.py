"""add_contact_attributes_column

Revision ID: d7e4f5a8b901
Revises: c6d3e4f7b890
Create Date: 2026-04-09 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd7e4f5a8b901'
down_revision: Union[str, None] = 'c6d3e4f7b890'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('attributes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('contacts', 'attributes')
