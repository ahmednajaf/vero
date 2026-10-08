"""Immutable parse attempts, artifact verification, atomic page/table/chunk storage."""

import hashlib
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, Settings
from app.db.models import (
    Company,
    DocumentChunk,
    DocumentPage,
    DocumentTable,
    ExtractionRun,
    Report,
    ReportArtifact,
)
from app.parsing.contracts import PARSER_VERSION, ParseOptions, ParseResult
from app.parsing.engine import ParseFailure, canonical_json, text_hash, versions


def options_for(settings: Settings) -> ParseOptions:
    return ParseOptions(
        chunk_chars=settings.parse_chunk_chars,
        max_pages=settings.parse_max_pages,
        max_page_chars=settings.parse_max_page_chars,
        max_document_chars=settings.parse_max_document_chars,
        max_tables_per_page=settings.parse_max_tables_per_page,
        pdfplumber_fallback=settings.parse_pdfplumber_fallback,
    )


def run_worker(
    source: Path, output: Path, options: ParseOptions, timeout: int
) -> ParseResult:
    with output.with_suffix(".log").open("xb") as log:
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.parsing.worker",
                    str(source),
                    str(output),
                    options.model_dump_json(),
                ],
                cwd=BACKEND_DIR,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=log,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ParseFailure(
                "timeout",
                f"Parser exceeded {timeout}s and was stopped; no partial chunks committed",
            ) from exc
    if completed.returncode != 0 or not output.is_file():
        raise ParseFailure(
            "worker_failed",
            f"Parser worker exited with code {completed.returncode}; no partial chunks committed",
        )
    if output.stat().st_size > 256 * 1024 * 1024:
        raise ParseFailure("output_limit", "Parser output exceeds the 256 MB limit")
    try:
        return ParseResult.model_validate_json(output.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ParseFailure(
            "worker_output", "Parser returned an invalid structured result"
        ) from exc


def verified_snapshot(
    report: Report, artifact: ReportArtifact | None, settings: Settings, target: Path
) -> None:
    if (
        report.status != "downloaded"
        or artifact is None
        or not report.storage_key
        or not report.content_sha256
    ):
        raise ParseFailure(
            "not_downloaded", "Report lacks a verified downloaded artifact"
        )
    if (report.content_sha256, report.storage_key, report.file_size_bytes) != (
        artifact.content_sha256,
        artifact.storage_key,
        artifact.file_size_bytes,
    ):
        raise ParseFailure("artifact_mismatch", "Report and artifact metadata disagree")
    root = settings.reports_root.resolve()
    source = (root / report.storage_key).resolve()
    if not source.is_relative_to(root):
        raise ParseFailure(
            "unsafe_path", "Artifact path escapes configured report storage"
        )
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as original, target.open("xb") as snapshot:
        for block in iter(lambda: original.read(1024 * 1024), b""):
            size += len(block)
            if size > settings.discovery_max_download_mb * 1024 * 1024:
                raise ParseFailure(
                    "input_limit", "PDF exceeds configured artifact size limit"
                )
            digest.update(block)
            snapshot.write(block)
    if (
        size != artifact.file_size_bytes
        or digest.hexdigest() != artifact.content_sha256
    ):
        raise ParseFailure(
            "checksum_mismatch",
            "Local PDF does not match its downloaded SHA-256/size; no text accepted",
        )


def persist_result(
    session: Session, report: Report, run: ExtractionRun, result: ParseResult
) -> None:
    index = 0
    for page in result.pages:
        saved = DocumentPage(
            report_id=report.id,
            parse_run_id=run.id,
            page_number=page.page_number,
            printed_page_label=page.printed_page_label,
            width_points=page.width_points,
            height_points=page.height_points,
            rotation=page.rotation,
            raw_text=page.raw_text,
            raw_text_sha256=page.raw_text_sha256,
            ordered_text=page.ordered_text,
            ordered_text_sha256=page.ordered_text_sha256,
            text_characters=len(page.raw_text),
            status=page.status,
            headings=page.headings,
            layout=page.layout,
            warnings=[warning.model_dump() for warning in page.warnings],
            parser_name="pymupdf",
            parser_version=result.versions["pymupdf"],
        )
        if page.raw_text_sha256 != text_hash(
            page.raw_text
        ) or page.ordered_text_sha256 != text_hash(page.ordered_text):
            raise ParseFailure(
                "output_integrity", "Page text hash does not match parser output"
            )
        session.add(saved)
        session.flush()
        for table_index, table in enumerate(page.tables):
            if table.content_sha256 != text_hash(canonical_json(table.cells)):
                raise ParseFailure(
                    "output_integrity", "Table hash does not match extracted cells"
                )
            session.add(
                DocumentTable(
                    document_page_id=saved.id,
                    report_id=report.id,
                    parse_run_id=run.id,
                    page_number=page.page_number,
                    table_index=table_index,
                    row_count=len(table.cells),
                    column_count=max(map(len, table.cells)),
                    cells=table.cells,
                    bbox=table.bbox,
                    cell_bboxes=table.cell_bboxes,
                    header_metadata=table.header_metadata,
                    extraction_metadata=table.extraction_metadata,
                    content_sha256=table.content_sha256,
                    extraction_method=table.extraction_method,
                    parser_version=table.parser_version,
                )
            )
        for chunk in page.chunks:
            if chunk.text != page.ordered_text[
                chunk.start : chunk.end
            ] or chunk.text_sha256 != text_hash(chunk.text):
                raise ParseFailure(
                    "output_integrity",
                    "Chunk is not a hash-verified exact page-text slice",
                )
            session.add(
                DocumentChunk(
                    report_id=report.id,
                    parse_run_id=run.id,
                    document_page_id=saved.id,
                    chunk_index=index,
                    physical_page_start=page.page_number,
                    physical_page_end=page.page_number,
                    printed_page_label=page.printed_page_label,
                    section_title=chunk.section_heading,
                    text=chunk.text,
                    text_sha256=chunk.text_sha256,
                    chunk_type="text",
                    parser_name="pymupdf+page-provenance",
                    parser_version=PARSER_VERSION,
                    source_char_start=chunk.start,
                    source_char_end=chunk.end,
                    source_spans=chunk.source_spans,
                )
            )
            index += 1
    if [page.page_number for page in result.pages] != list(
        range(1, len(result.pages) + 1)
    ):
        raise ParseFailure(
            "output_integrity", "Parser output has missing or reordered pages"
        )
    report.parse_status = result.status
    if result.pages:
        report.page_count = len(result.pages)
    run.status = "failed" if result.status == "failed" else "succeeded"
    run.error_code, run.error_summary = result.error_code, result.error_summary
    run.finished_at = datetime.now(UTC)
    run.output_summary = {
        **result.quality,
        "parse_status": result.status,
        "versions": result.versions,
        "warnings": [warning.model_dump() for warning in result.warnings],
    }


def parse_report(
    engine: Engine, report_id: UUID, settings: Settings, *, force: bool = False
) -> dict[str, Any]:
    options = options_for(settings)
    profile = text_hash(
        canonical_json(
            {
                "versions": versions(),
                "options": options.model_dump(),
                "timeout_seconds": settings.parse_timeout_seconds,
            }
        )
    )
    lock_key = f"parse-report:{report_id}"
    with engine.connect() as connection:
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
            {"key": lock_key},
        )
        connection.commit()
        if not acquired:
            return {
                "report_id": str(report_id),
                "status": "busy",
                "message": "Another parser owns this report",
            }
        try:
            with Session(connection, expire_on_commit=False) as session:
                report = session.get(Report, report_id)
                if report is None:
                    raise ValueError("Report not found")
                if not report.content_sha256:
                    raise ValueError(
                        "Report has no recorded input checksum; download it before parsing"
                    )
                latest_id = session.scalar(
                    select(ExtractionRun.id)
                    .where(
                        ExtractionRun.report_id == report.id,
                        ExtractionRun.stage == "parsing",
                    )
                    .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
                    .limit(1)
                )
                prior = session.scalar(
                    select(ExtractionRun)
                    .where(
                        ExtractionRun.report_id == report.id,
                        ExtractionRun.stage == "parsing",
                        ExtractionRun.input_sha256 == report.content_sha256,
                        ExtractionRun.parameters["profile_sha256"].astext == profile,
                        ExtractionRun.status == "succeeded",
                    )
                    .order_by(ExtractionRun.created_at.desc())
                    .limit(1)
                )
                # Verify the artifact even on idempotent skips; changed local bytes
                # must not masquerade as a successfully parsed existing version.
                with tempfile.TemporaryDirectory(prefix="sbi-parse-") as temporary:
                    work = Path(temporary)
                    artifact = (
                        session.get(ReportArtifact, report.artifact_id)
                        if report.artifact_id
                        else None
                    )
                    snapshot_error: Exception | None = None
                    try:
                        verified_snapshot(
                            report, artifact, settings, work / "input.pdf"
                        )
                    except (ParseFailure, OSError) as exc:
                        snapshot_error = exc
                    if (
                        prior is not None
                        and prior.id == latest_id
                        and not force
                        and snapshot_error is None
                    ):
                        return {
                            "report_id": str(report.id),
                            "run_id": str(prior.id),
                            "status": "unchanged",
                            "quality": prior.output_summary,
                        }
                    # A session-level lock survived the commit. A previous running
                    # record without that lock is a crashed/interrupted attempt.
                    for abandoned in session.scalars(
                        select(ExtractionRun).where(
                            ExtractionRun.report_id == report.id,
                            ExtractionRun.stage == "parsing",
                            ExtractionRun.status == "running",
                        )
                    ):
                        abandoned.status, abandoned.error_code = "failed", "interrupted"
                        abandoned.error_summary, abandoned.finished_at = (
                            "Previous parser no longer holds the report lock",
                            datetime.now(UTC),
                        )
                    run = ExtractionRun(
                        report_id=report.id,
                        stage="parsing",
                        status="running",
                        idempotency_key=f"{profile}:{uuid4().hex}",
                        input_sha256=report.content_sha256,
                        schema_version="page-provenance-v1",
                        code_version=PARSER_VERSION,
                        parameters={
                            "profile_sha256": profile,
                            "options": options.model_dump(),
                            "versions": versions(),
                            "source_url": report.source_url,
                            "artifact_id": (
                                str(report.artifact_id) if report.artifact_id else None
                            ),
                            "ocr": False,
                        },
                        started_at=datetime.now(UTC),
                    )
                    session.add(run)
                    report.parse_status = "running"
                    session.commit()
                    try:
                        if snapshot_error:
                            raise snapshot_error
                        result = run_worker(
                            work / "input.pdf",
                            work / "output.json",
                            options,
                            settings.parse_timeout_seconds,
                        )
                        with session.begin_nested():
                            persist_result(session, report, run, result)
                            session.flush()
                        session.commit()
                    except (ParseFailure, OSError, ValueError) as exc:
                        session.rollback()
                        run.status, run.finished_at = "failed", datetime.now(UTC)
                        run.error_code = (
                            exc.code if isinstance(exc, ParseFailure) else "io_error"
                        )
                        run.error_summary = str(exc)[:500]
                        run.output_summary = {
                            "parse_status": "failed",
                            "ocr_performed": False,
                        }
                        report.parse_status = "failed"
                        session.commit()
                    return {
                        "report_id": str(report.id),
                        "run_id": str(run.id),
                        "status": report.parse_status,
                        "quality": run.output_summary,
                        "error_code": run.error_code,
                        "error_summary": run.error_summary,
                    }
        finally:
            connection.rollback()
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                {"key": lock_key},
            )
            connection.commit()


def parse_status(
    session: Session,
    *,
    report_ids: list[UUID] | None = None,
    year: int | None = None,
    examples: int = 0,
) -> dict[str, Any]:
    query = (
        select(Report, Company.company_name)
        .join(Company, Report.company_id == Company.id)
        .where(Report.status == "downloaded")
    )
    if report_ids:
        query = query.where(Report.id.in_(report_ids))
    if year is not None:
        query = query.where(Report.requested_year == year)
    items: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for report, name in session.execute(
        query.order_by(Company.company_name, Report.requested_year, Report.id)
    ):
        run = session.scalar(
            select(ExtractionRun)
            .where(
                ExtractionRun.report_id == report.id, ExtractionRun.stage == "parsing"
            )
            .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
            .limit(1)
        )
        item: dict[str, Any] = {
            "report_id": str(report.id),
            "company_name": name,
            "requested_year": report.requested_year,
            "source_url": report.source_url,
            "input_sha256": report.content_sha256,
            "status": report.parse_status,
            "run_id": str(run.id) if run else None,
            "run_state": run.status if run else None,
            "quality": run.output_summary if run else None,
            "error_code": run.error_code if run else None,
            "error_summary": run.error_summary if run else None,
            "finished_at": (
                run.finished_at.isoformat() if run and run.finished_at else None
            ),
        }
        counts[report.parse_status] = counts.get(report.parse_status, 0) + 1
        if examples and run:
            chunks = session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.parse_run_id == run.id)
                .order_by(DocumentChunk.chunk_index)
                .limit(examples)
            )
            item["chunk_examples"] = [
                {
                    "chunk_id": str(c.id),
                    "document_page_id": str(c.document_page_id),
                    "page_start": c.physical_page_start,
                    "page_end": c.physical_page_end,
                    "section_heading": c.section_title,
                    "source_char_start": c.source_char_start,
                    "source_char_end": c.source_char_end,
                    "chunk_hash": c.text_sha256,
                    "text": c.text,
                    "source_spans": c.source_spans,
                }
                for c in chunks
            ]
        items.append(item)
    return {"downloaded_reports": len(items), "counts": counts, "items": items}
