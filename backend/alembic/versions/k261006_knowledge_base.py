"""Full-report search, resumable acquisition and metered cited research.

Revision ID: k261006
Revises: e251002
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "k261006"
down_revision = "e251002"
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
        "knowledge_indexes",
        *identity(),
        sa.Column(
            "report_id",
            sa.Uuid,
            sa.ForeignKey("reports.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "parse_run_id",
            sa.Uuid,
            sa.ForeignKey("extraction_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("report_sha256", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("version", sa.String(30), nullable=False),
        sa.Column("quality", pg.JSONB, nullable=False),
    )
    op.create_table(
        "knowledge_passages",
        *identity(),
        sa.Column(
            "index_id",
            sa.Uuid,
            sa.ForeignKey("knowledge_indexes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "page_id",
            sa.Uuid,
            sa.ForeignKey("document_pages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("locator", pg.JSONB, nullable=False),
        sa.Column(
            "search_vector",
            pg.TSVECTOR,
            sa.Computed("to_tsvector('english'::regconfig, content)", persisted=True),
            nullable=False,
        ),
        sa.UniqueConstraint("index_id", "ordinal"),
        sa.CheckConstraint("kind IN ('text','table')", name="kind"),
        sa.CheckConstraint("ordinal >= 0 AND length(content) > 0", name="content"),
    )
    op.create_index(
        "ix_knowledge_passages_search",
        "knowledge_passages",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index("ix_knowledge_passages_page", "knowledge_passages", ["page_id"])
    op.create_table(
        "knowledge_jobs",
        *identity(),
        sa.Column(
            "company_id",
            sa.Uuid,
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "outcome", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.UniqueConstraint("company_id", "year"),
        sa.CheckConstraint(
            "year BETWEEN 2000 AND 2100 AND attempts >= 0", name="bounds"
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','partial','failed','needs_review','unavailable')",
            name="status",
        ),
    )
    op.create_index("ix_knowledge_jobs_status", "knowledge_jobs", ["status", "year"])
    op.create_table(
        "knowledge_answers",
        *identity(),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column(
            "payload", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("reserved_usd", sa.Numeric(16, 8), nullable=False),
        sa.Column("charged_usd", sa.Numeric(16, 8)),
        sa.Column(
            "usage", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("error_code", sa.String(80)),
        sa.CheckConstraint("status IN ('running','completed','failed')", name="status"),
        sa.CheckConstraint(
            "reserved_usd >= 0 AND (charged_usd IS NULL OR charged_usd >= 0)",
            name="cost",
        ),
    )
    op.create_index(
        "ix_knowledge_answers_budget", "knowledge_answers", ["created_at", "status"]
    )
    op.create_index(
        "ix_knowledge_answers_request_sha256", "knowledge_answers", ["request_sha256"]
    )
    op.execute("""
        CREATE FUNCTION sbi_check_knowledge_passage() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.content_sha256 <> encode(sha256(convert_to(NEW.content, 'UTF8')), 'hex')
            OR NOT EXISTS (
              SELECT 1 FROM knowledge_indexes i JOIN document_pages p
                ON p.report_id=i.report_id AND p.parse_run_id=i.parse_run_id
              WHERE i.id=NEW.index_id AND p.id=NEW.page_id
            ) THEN
            RAISE EXCEPTION 'Knowledge passage source identity or hash mismatch' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER check_knowledge_passage BEFORE INSERT OR UPDATE ON knowledge_passages
          FOR EACH ROW EXECUTE FUNCTION sbi_check_knowledge_passage();
    """)


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM knowledge_answers) OR EXISTS(SELECT 1 FROM knowledge_jobs)"
        )
    ):
        raise RuntimeError("Refuse to delete retained research or ingestion history")
    for table in (
        "knowledge_answers",
        "knowledge_jobs",
        "knowledge_passages",
        "knowledge_indexes",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION sbi_check_knowledge_passage()")
