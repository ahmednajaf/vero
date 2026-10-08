"""Permit the explicitly scoped pharmaceutical research sample.

Revision ID: e251001a
Revises: d40e179a21c6
"""

from alembic import op
import sqlalchemy as sa

revision = "e251001a"
down_revision = "d40e179a21c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_companies_sector"), "companies", type_="check")
    op.create_check_constraint(
        op.f("ck_companies_sector"),
        "companies",
        "sector IN ('Financial Services','Technology','Energy','Consumer / Retail','Industrials','Pharmaceuticals')",
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM companies WHERE sector='Pharmaceuticals')")
    ):
        raise RuntimeError("Refusing to remove a sector with retained company evidence")
    op.drop_constraint(op.f("ck_companies_sector"), "companies", type_="check")
    op.create_check_constraint(
        op.f("ck_companies_sector"),
        "companies",
        "sector IN ('Financial Services','Technology','Energy','Consumer / Retail','Industrials')",
    )
