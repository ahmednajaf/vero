"""Index every retained text page and table, without metric-catalogue filtering."""

import hashlib
import json
from typing import Any, Iterator
from uuid import UUID

from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    DocumentPage,
    DocumentTable,
    ExtractionRun,
    KnowledgeIndex,
    KnowledgePassage,
    Report,
)
from app.parsing.engine import canonical_json, text_hash

INDEX_VERSION = "full-report-v1"


def windows(value: str, maximum: int = 4000) -> Iterator[tuple[int, int, str]]:
    """Contiguous, lossless windows; no page is merged, dropped or truncated."""
    start = 0
    while start < len(value):
        end = min(len(value), start + maximum)
        if end < len(value):
            boundary = value.rfind("\n", start + maximum // 2, end)
            if boundary != -1:
                end = boundary + 1
        yield start, end, value[start:end]
        start = end


def latest_parse(session: Session, report: Report) -> ExtractionRun | None:
    return session.scalar(
        select(ExtractionRun)
        .where(ExtractionRun.report_id == report.id, ExtractionRun.stage == "parsing")
        .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
        .limit(1)
    )


def index_report(engine: Engine, report_id: UUID, settings: Settings) -> dict[str, Any]:
    with Session(engine) as session, session.begin():
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"knowledge-index:{report_id}"},
        )
        report = session.get(Report, report_id)
        if (
            not report
            or report.status != "downloaded"
            or report.source_policy != "official"
            or not report.storage_key
        ):
            raise ValueError("official_download_required")
        run = latest_parse(session, report)
        if (
            not run
            or run.status != "succeeded"
            or run.input_sha256 != report.content_sha256
        ):
            raise ValueError("current_parse_required")
        root = settings.reports_root.resolve()
        path = (root / report.storage_key).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("source_file_missing")
        with path.open("rb") as stream:
            if (
                hashlib.file_digest(stream, "sha256").hexdigest()
                != report.content_sha256
            ):
                raise ValueError("source_checksum_mismatch")
        pages = list(
            session.scalars(
                select(DocumentPage)
                .where(DocumentPage.parse_run_id == run.id)
                .order_by(DocumentPage.page_number)
            )
        )
        tables = list(
            session.scalars(
                select(DocumentTable)
                .where(DocumentTable.parse_run_id == run.id)
                .order_by(DocumentTable.page_number, DocumentTable.table_index)
            )
        )
        if not pages or [p.page_number for p in pages] != list(
            range(1, (report.page_count or 0) + 1)
        ):
            raise ValueError("incomplete_page_manifest")
        for page in pages:
            if (
                text_hash(page.raw_text) != page.raw_text_sha256
                or text_hash(page.ordered_text) != page.ordered_text_sha256
            ):
                raise ValueError("page_checksum_mismatch")
        for table in tables:
            if text_hash(canonical_json(table.cells)) != table.content_sha256:
                raise ValueError("table_checksum_mismatch")
        fingerprint = text_hash(
            canonical_json(
                [
                    INDEX_VERSION,
                    str(run.id),
                    report.content_sha256,
                    report.source_url,
                    [
                        [str(p.id), p.raw_text_sha256, p.ordered_text_sha256, p.status]
                        for p in pages
                    ],
                    [[str(t.id), t.content_sha256] for t in tables],
                ]
            )
        )
        existing = session.scalar(
            select(KnowledgeIndex).where(KnowledgeIndex.report_id == report_id)
        )
        if existing and existing.fingerprint == fingerprint:
            return {
                "report_id": str(report_id),
                "status": "unchanged",
                "quality": existing.quality,
            }
        if existing:
            # Only replace this derived index. Source pages, parse runs and answers survive.
            session.execute(
                delete(KnowledgePassage).where(KnowledgePassage.index_id == existing.id)
            )
            index = existing
        else:
            index = KnowledgeIndex(report_id=report_id)
            session.add(index)
        index.parse_run_id, index.report_sha256 = run.id, report.content_sha256 or ""
        index.fingerprint, index.version, index.source_url = (
            fingerprint,
            INDEX_VERSION,
            report.source_url,
        )
        quality: dict[str, Any] = {
            "pages_total": len(pages),
            "pages_with_text": sum(bool(p.raw_text.strip()) for p in pages),
            "pages_needing_ocr": [
                p.page_number for p in pages if p.status == "needs_ocr"
            ],
            "failed_pages": [p.page_number for p in pages if p.status == "failed"],
            "text_characters": sum(len(p.raw_text) for p in pages),
            "tables": len(tables),
            "parser_status": report.parse_status,
            "parse_warnings": run.output_summary,
            "coverage": "complete_extracted_text"
            if all(p.status == "parsed" for p in pages)
            else "partial_extracted_text",
            "review_state": "unreviewed_source_text",
            "ocr_performed": False,
        }
        index.quality = quality
        session.flush()
        ordinal = 0

        def add(
            page_id: UUID, kind: str, content: str, locator: dict[str, object]
        ) -> None:
            nonlocal ordinal
            if not content:
                return
            session.add(
                KnowledgePassage(
                    index_id=index.id,
                    page_id=page_id,
                    ordinal=ordinal,
                    kind=kind,
                    content=content,
                    content_sha256=text_hash(content),
                    locator=locator,
                )
            )
            ordinal += 1

        for page in pages:
            # Raw text is exhaustive. Structured tables supplement, not replace it.
            for start, end, value in windows(page.raw_text):
                add(
                    page.id,
                    "text",
                    value,
                    {"layer": "raw_text", "start": start, "end": end},
                )
        for table in tables:
            # JSON arrays retain empty cells and column positions. Headers are NOT guessed.
            for row_number, cells in enumerate(table.cells):
                value = json.dumps(cells, ensure_ascii=False)
                for start, end, fragment in windows(value):
                    add(
                        table.document_page_id,
                        "table",
                        fragment,
                        {
                            "table_id": str(table.id),
                            "row": row_number,
                            "start": start,
                            "end": end,
                            "table_sha256": table.content_sha256,
                            "header_metadata": table.header_metadata,
                            "validation_state": table.validation_state,
                        },
                    )
        index.quality = {**quality, "passages": ordinal}
        return {
            "report_id": str(report_id),
            "status": "indexed",
            "quality": index.quality,
        }
