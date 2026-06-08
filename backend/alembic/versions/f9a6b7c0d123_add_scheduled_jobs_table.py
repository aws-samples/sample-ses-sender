"""add_scheduled_jobs_table

Revision ID: f9a6b7c0d123
Revises: e8f5a6b9c012
Create Date: 2026-04-14 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "f9a6b7c0d123"
down_revision = "e8f5a6b9c012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), index=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("template_name", sa.String(255)),
        sa.Column("group_name", sa.String(255)),
        sa.Column("schedule_type", sa.String(16), nullable=False),
        sa.Column("scheduled_time", sa.DateTime(), nullable=False),
        sa.Column("cron_hour", sa.Integer(), server_default="9"),
        sa.Column("cron_minute", sa.Integer(), server_default="0"),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), server_default="active"),
        sa.Column("next_run_at", sa.DateTime(), index=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("run_count", sa.Integer(), server_default="0"),
        sa.Column("last_batch_id", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("scheduled_jobs")
