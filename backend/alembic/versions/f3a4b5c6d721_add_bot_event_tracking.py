"""add bot event tracking to sending_job_details

支持 SES isBotEvent 字段（2026-08 新增）：区分真人与自动化系统触发的 Open/Click。

Revision ID: f3a4b5c6d721
Revises: e2f3a4b5c610
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa

revision = "f3a4b5c6d721"
down_revision = "e2f3a4b5c610"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sending_job_details", sa.Column("human_open_count", sa.Integer(), server_default="0", nullable=True))
    op.add_column("sending_job_details", sa.Column("last_open_is_bot", sa.Boolean(), nullable=True))
    op.add_column("sending_job_details", sa.Column("human_click_count", sa.Integer(), server_default="0", nullable=True))
    op.add_column("sending_job_details", sa.Column("last_click_is_bot", sa.Boolean(), nullable=True))
    # 历史数据回填：此前未区分机器人，将已有 open/click 视为真人计数
    op.execute("UPDATE sending_job_details SET human_open_count = open_count WHERE open_count > 0")
    op.execute("UPDATE sending_job_details SET human_click_count = click_count WHERE click_count > 0")


def downgrade():
    op.drop_column("sending_job_details", "last_click_is_bot")
    op.drop_column("sending_job_details", "human_click_count")
    op.drop_column("sending_job_details", "last_open_is_bot")
    op.drop_column("sending_job_details", "human_open_count")
