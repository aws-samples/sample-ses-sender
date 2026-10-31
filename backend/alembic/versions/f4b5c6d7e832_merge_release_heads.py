"""merge v1.3 and contact validation migration branches

Revision ID: f4b5c6d7e832
Revises: e1f2a3b4c561, f3a4b5c6d721
Create Date: 2026-10-31
"""

from alembic import op
import sqlalchemy as sa

revision = "f4b5c6d7e832"
down_revision = ("e1f2a3b4c561", "f3a4b5c6d721")
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name not in ("mysql", "mariadb"):
        return

    # The e1 downgrade restores a single-column index so MySQL can keep the
    # contacts.group_id foreign key while dropping the composite index.  If
    # that branch is upgraded again, both indexes can remain.  Normalize the
    # merged schema only when the two indexes have their exact expected shape.
    indexes = {
        index["name"]: tuple(index["column_names"])
        for index in sa.inspect(bind).get_indexes("contacts")
    }
    if (
        indexes.get("ix_contacts_group_id") == ("group_id",)
        and indexes.get("ix_contacts_group_id_id") == ("group_id", "id")
    ):
        op.drop_index("ix_contacts_group_id", table_name="contacts")


def downgrade():
    pass
