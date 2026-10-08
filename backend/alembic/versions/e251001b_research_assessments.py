"""Separate source-fact review from bounded research comparability."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e251001b"
down_revision = "e251001a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_assessments",
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
        sa.Column("study_id", sa.String(80), nullable=False),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("metric_code", sa.String(100), nullable=False),
        sa.Column(
            "observation_id",
            sa.Uuid(),
            sa.ForeignKey("metric_observations.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "target_id", sa.Uuid(), sa.ForeignKey("targets.id", ondelete="RESTRICT")
        ),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("comparison_group", sa.String(200)),
        sa.Column("comparability_note", sa.Text(), nullable=False),
        sa.Column("review", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("study_id", "company_id", "metric_code"),
        sa.CheckConstraint(
            "status IN ('NOT_ASSESSED','NOT_FOUND_IN_REVIEWED_SOURCES','NOT_REPORTED','NOT_COMPARABLE','VALIDATED','NEEDS_REVIEW')",
            name="status",
        ),
        sa.CheckConstraint(
            "num_nonnulls(observation_id, target_id) <= 1", name="one_value"
        ),
        sa.CheckConstraint(
            "status <> 'VALIDATED' OR num_nonnulls(observation_id, target_id) = 1",
            name="validated_evidence",
        ),
        sa.CheckConstraint(
            "status <> 'VALIDATED' OR comparison_group IS NOT NULL",
            name="stated_comparison",
        ),
    )
    op.create_index(
        "ix_research_assessments_study_status",
        "research_assessments",
        ["study_id", "status"],
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM research_assessments)")
    ):
        raise RuntimeError(
            "Retained research decisions require an explicit archival plan"
        )
    op.drop_table("research_assessments")
