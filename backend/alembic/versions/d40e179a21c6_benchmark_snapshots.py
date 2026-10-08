"""Reviewed comparison context and separately persisted benchmark components.

Revision ID: d40e179a21c6
Revises: 6ccc1d6cca42
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d40e179a21c6"
down_revision = "6ccc1d6cca42"
branch_labels = None
depends_on = None


def identity() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    # Reviews must follow last-edit triggers even inside one transaction.
    # Historical events are unchanged.
    op.alter_column(
        "validation_events", "created_at", server_default=sa.text("clock_timestamp()")
    )
    op.add_column(
        "metric_observations",
        sa.Column(
            "comparison_context",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_table(
        "benchmark_snapshots",
        sa.Column("reporting_year", sa.Integer(), nullable=False),
        sa.Column("methodology_version", sa.String(80), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("results", postgresql.JSONB(), nullable=False),
        *identity(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_benchmark_snapshots")),
        sa.UniqueConstraint(
            "input_sha256", name=op.f("uq_benchmark_snapshots_input_sha256")
        ),
        sa.CheckConstraint(
            "reporting_year BETWEEN 2000 AND 2100",
            name=op.f("ck_benchmark_snapshots_year"),
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_benchmark_snapshots_checksum"),
        ),
    )
    op.create_index(
        "ix_benchmark_snapshots_year_created",
        "benchmark_snapshots",
        ["reporting_year", "created_at"],
    )
    op.create_table(
        "benchmark_components",
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("component", sa.String(80), nullable=False),
        sa.Column("score", sa.Numeric(12, 6), nullable=True),
        sa.Column("weight", sa.Numeric(5, 4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        *identity(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_benchmark_components")),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["benchmark_snapshots.id"],
            name=op.f("fk_benchmark_components_snapshot_id_benchmark_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_benchmark_components_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            "company_id",
            "component",
            name=op.f("uq_benchmark_components_snapshot_id"),
        ),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 0 AND 100",
            name=op.f("ck_benchmark_components_score"),
        ),
        sa.CheckConstraint(
            "weight BETWEEN 0 AND 1", name=op.f("ck_benchmark_components_weight")
        ),
    )
    op.create_index(
        "ix_benchmark_components_company_snapshot",
        "benchmark_components",
        ["company_id", "snapshot_id"],
    )
    op.execute("""
        CREATE FUNCTION sbi_protect_benchmark_history() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'benchmark snapshots and components are append-only' USING ERRCODE = '23514'; END;
        $$
    """)
    for table in ("benchmark_snapshots", "benchmark_components"):
        op.execute(
            f"CREATE TRIGGER benchmark_history_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION sbi_protect_benchmark_history()"
        )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM benchmark_snapshots)")
    ):
        raise RuntimeError("Refusing to discard stored benchmark audit history")
    op.drop_table("benchmark_components")
    op.drop_table("benchmark_snapshots")
    op.execute("DROP FUNCTION sbi_protect_benchmark_history()")
    op.drop_column("metric_observations", "comparison_context")
    op.alter_column("validation_events", "created_at", server_default=sa.text("now()"))
