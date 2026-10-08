"""Add customer benchmark sessions and AI call/cache provenance. Preserve research."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e251002"
down_revision = "e251001c"
branch_labels = None
depends_on = None


def identity():
    return [
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade():
    op.create_table(
        "benchmark_sessions",
        *identity(),
        sa.Column("status", sa.String(24), nullable=False, server_default="uploading"),
        sa.Column("reporting_year", sa.Integer, nullable=False),
        sa.Column("is_demo", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("unlocked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "stages",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("result", postgresql.JSONB),
        sa.Column("error_code", sa.String(80)),
        sa.Column("cache_replay", sa.Boolean, nullable=False, server_default="false"),
        sa.CheckConstraint(
            "status IN ('uploading','queued','running','failed','ready')", name="status"
        ),
    )
    op.create_index("ix_benchmark_sessions_status", "benchmark_sessions", ["status"])
    op.create_table(
        "benchmark_documents",
        *identity(),
        sa.Column(
            "session_id",
            sa.Uuid,
            sa.ForeignKey("benchmark_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("ticker", sa.String(30)),
        sa.Column("sector", sa.String(100)),
        sa.Column("primary", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("filename", sa.String(240), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text),
        sa.Column(
            "report_id", sa.Uuid, sa.ForeignKey("reports.id", ondelete="RESTRICT")
        ),
        sa.UniqueConstraint("session_id", "sha256", name="uq_benchmark_document_hash"),
        sa.UniqueConstraint("session_id", "company_name", name="uq_benchmark_document_company"),
    )
    op.create_index(
        "ix_benchmark_documents_session_id", "benchmark_documents", ["session_id"]
    )
    op.create_table(
        "analysis_cache",
        *identity(),
        sa.Column("cache_key", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
    )
    op.create_table(
        "ai_calls",
        *identity(),
        sa.Column(
            "session_id",
            sa.Uuid,
            sa.ForeignKey("benchmark_sessions.id", ondelete="SET NULL"),
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("task_type", sa.String(30), nullable=False),
        sa.Column("latency_ms", sa.Float, nullable=False),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("estimated_cost", sa.Numeric(16, 8)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("fallback_from", sa.String(200)),
    )
    op.create_index("ix_ai_calls_session_id", "ai_calls", ["session_id"])


def downgrade():
    for table in (
        "ai_calls",
        "analysis_cache",
        "benchmark_documents",
        "benchmark_sessions",
    ):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")):
            raise RuntimeError("Refuse to delete retained customer analysis data")
    for table in (
        "ai_calls",
        "analysis_cache",
        "benchmark_documents",
        "benchmark_sessions",
    ):
        op.drop_table(table)
