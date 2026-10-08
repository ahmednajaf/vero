"""Allow exact raw-text evidence slices without changing immutable parsed pages."""

from alembic import op
import sqlalchemy as sa

revision = "e251001c"
down_revision = "e251001b"
branch_labels = None
depends_on = None


def trigger(raw: bool):
    source = (
        "CASE WHEN NEW.source_text_layer = 'raw_text' THEN raw_text ELSE ordered_text END"
        if raw
        else "ordered_text"
    )
    op.execute(
        f"""CREATE OR REPLACE FUNCTION sbi_check_page_chunk() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE page_text text;
    BEGIN
      IF NEW.document_page_id IS NOT NULL THEN
        SELECT {source} INTO page_text FROM document_pages WHERE id = NEW.document_page_id;
        IF page_text IS NULL OR NEW.source_char_end > char_length(page_text)
          OR substring(page_text FROM NEW.source_char_start + 1 FOR NEW.source_char_end - NEW.source_char_start) IS DISTINCT FROM NEW.text
          OR encode(sha256(convert_to(NEW.text, 'UTF8')), 'hex') <> NEW.text_sha256 THEN
          RAISE EXCEPTION 'Chunk must be a hash-verified exact slice of its source page' USING ERRCODE = '23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$"""
    )


def upgrade():
    op.add_column(
        "document_chunks",
        sa.Column(
            "source_text_layer",
            sa.String(20),
            nullable=False,
            server_default="ordered_text",
        ),
    )
    op.create_check_constraint(
        "source_text_layer",
        "document_chunks",
        "source_text_layer IN ('ordered_text','raw_text')",
    )
    trigger(True)


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM document_chunks WHERE source_text_layer='raw_text')"
        )
    ):
        raise RuntimeError("Cannot remove a provenance layer with retained evidence")
    trigger(False)
    op.drop_constraint(
        op.f("ck_document_chunks_source_text_layer"), "document_chunks", type_="check"
    )
    op.drop_column("document_chunks", "source_text_layer")
