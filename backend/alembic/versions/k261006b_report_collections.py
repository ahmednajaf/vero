"""Durable bulk report collection cohorts; no metric or benchmark promotion."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "k261006b"
down_revision = "k261006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "report_collections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), server_default="pending", nullable=False),
        sa.Column("company_ids", postgresql.JSONB(), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column(
            "results",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "year BETWEEN 2000 AND 2100", name="ck_report_collections_year"
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','completed_with_gaps','interrupted')",
            name="ck_report_collections_status",
        ),
    )
    op.create_index(
        "ix_report_collections_status", "report_collections", ["status", "created_at"]
    )


def downgrade():
    op.drop_table("report_collections")
