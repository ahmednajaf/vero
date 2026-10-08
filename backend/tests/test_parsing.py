import hashlib
import json
import subprocess
from unittest.mock import patch
from uuid import uuid4

import pymupdf
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    Company,
    DocumentChunk,
    DocumentPage,
    DocumentTable,
    ExtractionRun,
    MetricObservation,
    Report,
    ReportArtifact,
)
from app.parsing.contracts import ParseOptions
from app.parsing.engine import ParseFailure, canonical_json, parse_pdf, text_hash
from app.parsing.service import parse_report, parse_status, run_worker
from app.services.company_import import import_companies
from pdf_fixtures import build_fixtures


@pytest.fixture(scope="session")
def pdfs(tmp_path_factory):
    return build_fixtures(tmp_path_factory.mktemp("pdf-fixtures"))


def test_text_pdf_preserves_all_pages_raw_text_offsets_and_hashes(pdfs):
    result = parse_pdf(pdfs["text"], ParseOptions(chunk_chars=300))
    assert result.status == "parsed"
    assert result.quality["pages_total"] == result.quality["pages_with_text"] == 2
    assert result.quality["text_characters"] == sum(
        len(p.raw_text) for p in result.pages
    )
    assert result.quality["ocr_performed"] is False
    for page in result.pages:
        with pymupdf.open(pdfs["text"]) as pdf:
            assert page.raw_text == pdf[page.page_number - 1].get_text(
                "text", sort=False
            )
        assert "".join(chunk.text for chunk in page.chunks) == page.ordered_text
        assert page.headings
        assert page.raw_text_sha256 == text_hash(page.raw_text)
        assert page.ordered_text_sha256 == text_hash(page.ordered_text)
        for chunk in page.chunks:
            assert chunk.text == page.ordered_text[chunk.start : chunk.end]
            assert chunk.text_sha256 == text_hash(chunk.text)
            assert len(chunk.text) <= 300 and chunk.section_heading
            assert f"PAGE_{3 - page.page_number}" not in chunk.text
            assert chunk.source_spans


def test_multi_column_order_is_not_row_interleaving(pdfs):
    result = parse_pdf(pdfs["multi_column"])
    page = result.pages[0]
    assert page.raw_text.index("RIGHT_00") < page.raw_text.index("LEFT_11")
    assert page.ordered_text.index("LEFT_11") < page.ordered_text.index("RIGHT_00")
    assert page.ordered_text.index("spanning heading") < page.ordered_text.index(
        "LEFT_00"
    )
    assert page.ordered_text.index("RIGHT_11") < page.ordered_text.index(
        "Footer retained"
    )
    assert len(page.layout["lines"]) == 26


def test_table_heavy_pdf_structured_cells_and_fallback(pdfs):
    result = parse_pdf(pdfs["tables"])
    assert result.quality["table_count"] >= 2
    assert result.pages[0].tables[0].extraction_method == "pymupdf.lines_strict"
    assert result.pages[1].tables[0].extraction_method == "pdfplumber.text_alignment"
    assert any(w.code == "table_fallback" for w in result.warnings)
    for page in result.pages[:2]:
        table = page.tables[0]
        assert table.content_sha256 == text_hash(canonical_json(table.cells))
        assert len(table.bbox) == 4 and table.cell_bboxes
        assert any("123.4" in row for row in table.cells)
        assert table.extraction_metadata["validation_state"] == "needs_review"
        assert all(
            cell is None or isinstance(cell, str) for row in table.cells for cell in row
        )
    # The blank cell is not imputed to zero.
    assert result.pages[0].tables[0].cells[2][2] in (None, "")


def test_side_by_side_horizontal_rule_tables_do_not_merge(pdfs):
    page = parse_pdf(pdfs["tables"]).pages[2]
    assert len(page.tables) == 2
    assert all(
        t.extraction_method == "pymupdf.horizontal_rules_whitespace"
        for t in page.tables
    )
    cells = [canonical_json(t.cells) for t in page.tables]
    assert any("LEFT A" in c and "RIGHT A" not in c for c in cells)
    assert any("RIGHT A" in c and "LEFT A" not in c for c in cells)
    assert page.ordered_text.index("LEFT C") < page.ordered_text.index("RIGHT A")
    assert (
        page.ordered_text.index("LEFT A")
        < page.ordered_text.index("123")
        < page.ordered_text.index("LEFT B")
    )


@pytest.mark.parametrize("name", ["empty", "scanned"])
def test_absent_text_needs_ocr_but_no_ocr_is_called(pdfs, name):
    with patch.object(
        pymupdf.Page,
        "get_textpage_ocr",
        side_effect=AssertionError("OCR must never run"),
    ):
        result = parse_pdf(pdfs[name])
    assert result.status == "needs_ocr" and result.pages[0].status == "needs_ocr"
    assert (
        result.quality["pages_with_text"] == 0
        and result.quality["text_characters"] == 0
    )
    assert result.quality["pages_needing_ocr"] == 1 and not result.pages[0].chunks
    assert result.quality["ocr_performed"] is False
    assert result.pages[0].layout["image_count"] == (1 if name == "scanned" else 0)


def test_malformed_pdf_records_failure_not_needs_ocr(pdfs):
    result = parse_pdf(pdfs["malformed"])
    assert result.status == "failed" and result.error_code == "invalid_pdf"
    assert result.pages == [] and result.quality["pages_total"] is None


def test_limits_do_not_silently_truncate(pdfs):
    result = parse_pdf(pdfs["text"], ParseOptions(max_pages=1))
    assert result.status == "failed" and result.error_code == "page_limit"
    assert result.pages == []
    result = parse_pdf(pdfs["text"], ParseOptions(max_document_chars=1000))
    assert result.status == "failed" and result.error_code == "document_text_limit"


def test_hashes_and_chunks_are_deterministic(pdfs):
    first = parse_pdf(pdfs["multi_column"])
    second = parse_pdf(pdfs["multi_column"])
    assert first == second


def test_worker_timeout_and_invalid_output_are_explicit(tmp_path, pdfs):
    with patch(
        "app.parsing.service.subprocess.run",
        side_effect=subprocess.TimeoutExpired("parser", 1),
    ):
        with pytest.raises(ParseFailure, match="exceeded"):
            run_worker(pdfs["text"], tmp_path / "out.json", ParseOptions(), 1)


@pytest.fixture
def downloaded(db_engine, company_row, csv_file, pdfs, tmp_path):
    assert import_companies(csv_file([company_row]), db_engine).committed
    config = Settings(
        _env_file=None, reports_root=tmp_path / "reports", parse_chunk_chars=300
    )

    def create(name="text"):
        data = pdfs[name].read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        with Session(db_engine, expire_on_commit=False) as session:
            company = session.scalar(select(Company))
            path = config.reports_root / str(company.id) / "2025" / f"{checksum}.pdf"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            artifact = session.scalar(
                select(ReportArtifact).where(ReportArtifact.content_sha256 == checksum)
            )
            if not artifact:
                artifact = ReportArtifact(
                    content_sha256=checksum,
                    storage_key=str(path.relative_to(config.reports_root)),
                    file_size_bytes=len(data),
                    mime_type="application/pdf",
                )
                session.add(artifact)
                session.flush()
            report = Report(
                company_id=company.id,
                title=f"Fictional {name} report",
                report_type="sustainability",
                reporting_year=None,
                requested_year=2025,
                source_url=f"https://example.com/{name}.pdf",
                artifact_id=artifact.id,
                content_sha256=checksum,
                storage_key=artifact.storage_key,
                file_size_bytes=len(data),
                status="downloaded",
                download_status="downloaded",
            )
            session.add(report)
            session.commit()
            return report.id, path

    return create, config


def test_persistence_idempotence_and_versioned_rerun(db_engine, downloaded):
    create, config = downloaded
    report_id, path = create()
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    first = parse_report(db_engine, report_id, config)
    assert first["status"] == "parsed"
    repeated = parse_report(db_engine, report_id, config)
    assert repeated["status"] == "unchanged" and repeated["run_id"] == first["run_id"]
    forced = parse_report(db_engine, report_id, config, force=True)
    assert forced["run_id"] != first["run_id"]
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(ExtractionRun)) == 2
        assert session.scalar(select(func.count()).select_from(DocumentPage)) == 4
        for chunk in session.scalars(select(DocumentChunk)):
            page = session.get(DocumentPage, chunk.document_page_id)
            assert (
                chunk.physical_page_start == chunk.physical_page_end == page.page_number
            )
            assert (
                chunk.text
                == page.ordered_text[chunk.source_char_start : chunk.source_char_end]
            )
            assert page.report_id == chunk.report_id == report_id
            assert page.parse_run_id == chunk.parse_run_id
        assert session.scalar(select(func.count()).select_from(MetricObservation)) == 0
        summary = parse_status(session, examples=1)
        assert summary["downloaded_reports"] == 1
        assert summary["items"][0]["run_id"] == forced["run_id"]
        assert len(summary["items"][0]["chunk_examples"]) == 1
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original_hash


def test_visual_page_review_is_hash_bound_and_preserves_parser_warnings(
    db_engine, downloaded, tmp_path
):
    from uuid import UUID
    from app.parsing.review import save_review, reviewed_decorative_pages

    create, config = downloaded
    report_id, path = create("empty")
    result = parse_report(db_engine, report_id, config)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = {
        "report_id": str(report_id),
        "parse_run_id": result["run_id"],
        "document_sha256": checksum,
        "reviewed_by": "test visual reviewer",
        "pages": [
            {
                "page_number": 1,
                "disposition": "decorative_no_metric_data",
                "reason": "Fixture page is blank and contains no report data after visual review.",
            }
        ],
    }
    manifest = tmp_path / "review.json"
    manifest.write_text(json.dumps(payload))
    review = save_review(db_engine, manifest)
    assert save_review(db_engine, manifest)["status"] == "unchanged"
    with Session(db_engine) as session:
        assert reviewed_decorative_pages(
            session, report_id, UUID(result["run_id"]), checksum
        ) == {1: review["review_run_id"]}
        assert (
            reviewed_decorative_pages(
                session, report_id, UUID(result["run_id"]), "f" * 64
            )
            == {}
        )
        assert session.get(Report, report_id).parse_status == "needs_ocr"
        assert session.scalar(select(DocumentPage)).status == "needs_ocr"
    payload["document_sha256"] = "f" * 64
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="checksum"):
        save_review(db_engine, manifest)


def test_tables_and_needs_ocr_persist_separately(db_engine, downloaded):
    create, config = downloaded
    table_report, _ = create("tables")
    scan_report, _ = create("scanned")
    assert parse_report(db_engine, table_report, config)["status"] == "needs_review"
    assert parse_report(db_engine, scan_report, config)["status"] == "needs_ocr"
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(DocumentTable)) >= 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.report_id == scan_report)
            )
            == 0
        )
        table = session.scalar(select(DocumentTable))
        assert table.validation_state == "needs_review"


def test_corrupt_artifact_cannot_reuse_a_successful_parse(db_engine, downloaded):
    create, config = downloaded
    report_id, path = create()
    assert parse_report(db_engine, report_id, config)["status"] == "parsed"
    path.write_bytes(b"%PDF changed since download")
    outcome = parse_report(db_engine, report_id, config)
    assert (
        outcome["status"] == "failed" and outcome["error_code"] == "checksum_mismatch"
    )
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(DocumentPage)) == 2
        assert session.scalar(select(func.count()).select_from(ExtractionRun)) == 2


def test_page_chunk_provenance_and_immutability_enforced_in_postgres(
    db_engine, downloaded
):
    create, config = downloaded
    report_id, _ = create()
    parse_report(db_engine, report_id, config)
    with Session(db_engine) as session:
        chunk = session.scalar(
            select(DocumentChunk).order_by(DocumentChunk.chunk_index)
        )
        page_id = chunk.document_page_id
        copied = {
            column.name: getattr(chunk, column.name)
            for column in DocumentChunk.__table__.columns
            if column.name not in ("id", "created_at", "updated_at")
        }
    for update in (
        {"physical_page_end": 2},
        {"text": "forged", "text_sha256": text_hash("forged")},
        {"source_char_end": 999999},
        {"parse_run_id": uuid4()},
    ):
        with Session(db_engine) as session, pytest.raises(IntegrityError):
            session.add(DocumentChunk(**(copied | {"chunk_index": 999} | update)))
            session.commit()
    for query in (
        "UPDATE document_pages SET raw_text='changed' WHERE id=:id",
        "DELETE FROM document_pages WHERE id=:id",
    ):
        with pytest.raises(IntegrityError), db_engine.begin() as connection:
            connection.execute(text(query), {"id": page_id})


def test_raw_text_review_chunks_still_require_exact_immutable_page_slices(db_engine, downloaded):
    create, config = downloaded
    report_id, _ = create("multi_column")
    parse_report(db_engine, report_id, config)
    with Session(db_engine) as session:
        original = session.scalar(select(DocumentChunk).order_by(DocumentChunk.chunk_index))
        page = session.get(DocumentPage, original.document_page_id)
        assert page.raw_text != page.ordered_text
        copied = {c.name:getattr(original,c.name) for c in DocumentChunk.__table__.columns if c.name not in ("id","created_at","updated_at")}
        excerpt = page.raw_text[:200]
        copied.update(chunk_index=999,source_text_layer="raw_text",source_char_start=0,source_char_end=200,text=excerpt,text_sha256=text_hash(excerpt))
        session.add(DocumentChunk(**copied))
        session.commit()
    for update in ({"text":"forged","text_sha256":text_hash("forged")},{"source_text_layer":"ordered_text"},{"source_text_layer":"invented"}):
        with Session(db_engine) as session, pytest.raises(IntegrityError):
            session.add(DocumentChunk(**(copied | {"chunk_index":1000} | update)))
            session.commit()


def test_failed_worker_does_not_commit_partial_pages_and_releases_lock(
    db_engine, downloaded
):
    create, config = downloaded
    report_id, _ = create()
    with patch(
        "app.parsing.service.run_worker",
        side_effect=ParseFailure("timeout", "Test worker timeout"),
    ):
        outcome = parse_report(db_engine, report_id, config)
    assert outcome["status"] == "failed" and outcome["error_code"] == "timeout"
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(DocumentPage)) == 0
    assert parse_report(db_engine, report_id, config)["status"] == "parsed"


def test_parser_lock_prevents_duplicate_concurrent_job(db_engine, downloaded):
    create, config = downloaded
    report_id, _ = create()
    with db_engine.connect() as connection:
        key = f"parse-report:{report_id}"
        connection.execute(
            text("SELECT pg_advisory_lock(hashtextextended(:key, 0))"), {"key": key}
        )
        connection.commit()
        try:
            assert parse_report(db_engine, report_id, config)["status"] == "busy"
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                {"key": key},
            )
            connection.commit()


def test_cli_parse_and_status_commands(db_engine, downloaded, monkeypatch, capsys):
    from app.cli import main

    create, config = downloaded
    report_id, _ = create()
    monkeypatch.setattr("app.cli.get_settings", lambda: config)
    monkeypatch.setattr("app.cli.create_database_engine", lambda _: db_engine)
    assert main(["parse-reports", "--report", str(report_id)]) == 0
    assert '"reports_processed": 1' in capsys.readouterr().out
    assert main(["parse-status", "--report", str(report_id), "--examples", "1"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["items"][0]["status"] == "parsed"
    assert summary["items"][0]["chunk_examples"][0]["page_start"] == 1
