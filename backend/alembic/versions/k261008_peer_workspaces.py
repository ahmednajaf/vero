"""Saved peer research; existing evidence and metric tables are unchanged."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "k261008"
down_revision = "k261006b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "peer_briefings",
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
        sa.Column(
            "primary_company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(24), server_default="pending", nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("sections", postgresql.JSONB(), nullable=False),
        sa.Column("source_signature", sa.String(64), nullable=False),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending','running','paused','ready','partial','failed')",
            name="ck_peer_briefings_status",
        ),
    )
    op.create_index(
        "ix_peer_briefings_company_created",
        "peer_briefings",
        ["primary_company_id", "created_at"],
    )


def downgrade():
    op.drop_table("peer_briefings")
