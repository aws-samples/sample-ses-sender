"""Add immutable contact selection snapshots and group/status lookup indexes.

Revision ID: e1f2a3b4c561
Revises: d0e1f2a3b450
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c561"
down_revision = "d0e1f2a3b450"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contact_selections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("contact_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_contact_selections_group_id", "contact_selections", ["group_id"])
    op.create_index("ix_contact_selections_expires_at", "contact_selections", ["expires_at"])
    op.create_table(
        "contact_selection_items",
        sa.Column("selection_id", sa.String(36), sa.ForeignKey("contact_selections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("contact_id", sa.Integer(), primary_key=True),
    )
    op.create_index("ix_contacts_group_id_id", "contacts", ["group_id", "id"])
    op.create_index("ix_sending_details_recipient_job", "sending_job_details", ["recipient", "job_id"])


def downgrade():
    # InnoDB may discard the old implicit group_id FK index when the composite
    # index is created. Restore a supporting index before removing that index.
    if op.get_bind().dialect.name in ("mysql", "mariadb"):
        indexes = sa.inspect(op.get_bind()).get_indexes("contacts")
        if not any(index["name"] != "ix_contacts_group_id_id" and
                   index["column_names"][:1] == ["group_id"] for index in indexes):
            op.create_index("ix_contacts_group_id", "contacts", ["group_id"])
    op.drop_index("ix_sending_details_recipient_job", table_name="sending_job_details")
    op.drop_index("ix_contacts_group_id_id", table_name="contacts")
    op.drop_table("contact_selection_items")
    op.drop_table("contact_selections")
