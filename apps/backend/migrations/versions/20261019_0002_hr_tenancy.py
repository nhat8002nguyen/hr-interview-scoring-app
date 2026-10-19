"""hr tenancy

Revision ID: 20261019_0002
Revises: 20261018_0001
Create Date: 2026-10-19 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20261019_0002"
down_revision: Union[str, Sequence[str], None] = "20261018_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "candidates",
        sa.Column("owner_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_candidates_owner_id_users",
        "candidates",
        "users",
        ["owner_id"],
        ["id"],
    )
    op.execute(
        "UPDATE candidates SET owner_id = (SELECT id FROM users ORDER BY id LIMIT 1) "
        "WHERE owner_id IS NULL"
    )
    op.alter_column("candidates", "owner_id", nullable=False)
    op.drop_index("ix_candidates_email", table_name="candidates")
    op.create_unique_constraint(
        "uq_candidates_owner_email", "candidates", ["owner_id", "email"]
    )
    op.drop_index("ix_candidates_external_ref", table_name="candidates")
    op.create_unique_constraint(
        "uq_candidates_owner_external_ref", "candidates", ["owner_id", "external_ref"]
    )
    op.create_index("ix_candidates_owner_id", "candidates", ["owner_id"])
    op.create_index("ix_candidates_owner_role", "candidates", ["owner_id", "role_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_candidates_owner_role", table_name="candidates")
    op.drop_index("ix_candidates_owner_id", table_name="candidates")
    op.drop_constraint(
        "uq_candidates_owner_external_ref", "candidates", type_="unique"
    )
    op.create_index(
        "ix_candidates_external_ref", "candidates", ["external_ref"], unique=True
    )
    op.drop_constraint("uq_candidates_owner_email", "candidates", type_="unique")
    op.create_index("ix_candidates_email", "candidates", ["email"], unique=True)
    op.drop_constraint("fk_candidates_owner_id_users", "candidates", type_="foreignkey")
    op.drop_column("candidates", "owner_id")
