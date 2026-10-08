"""Read-only source checks. Document identity signals are NOT metric validation."""

import hashlib
import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Company, DocumentPage, ExtractionRun, KnowledgeIndex, Report
from app.discovery.crawler import SUPPLEMENT
from app.knowledge.search import fresh

VERSION = "source-inspection-v1"
BASIS = re.compile(
    r"cover(?:ing|s)\s+(?:the\s+)?fiscal\s+year|reporting\s+period|"
    r"data\s+in\s+this\s+report|year\s+ended|consolidated\s+basis|"
    r"subsidiary\s+of|refer\s+to\s+.{0,60}(?:limited|entities)|"
    r"statement\s+is\s+extracted\s+from",
    re.I,
)


def inspect_source(
    session: Session,
    report_id: UUID,
    settings: Settings,
    *,
    verify_file: bool = False,
) -> dict[str, Any] | None:
    row = session.execute(
        select(Report, Company, KnowledgeIndex)
        .join(Company, Company.id == Report.company_id)
        .join(KnowledgeIndex, KnowledgeIndex.report_id == Report.id)
        .join(ExtractionRun, ExtractionRun.id == KnowledgeIndex.parse_run_id)
        .where(Report.id == report_id, *fresh())
    ).first()
    if row is None:
        return None
    report, company, index = row
    pages = list(
        session.scalars(
            select(DocumentPage)
            .where(
                DocumentPage.parse_run_id == index.parse_run_id,
                DocumentPage.page_number <= 8,
            )
            .order_by(DocumentPage.page_number)
        )
    )
    opening = []
    basis: list[dict[str, Any]] = []
    for page in pages:
        if page.page_number <= 2:
            opening.append(
                {
                    "page": page.page_number,
                    "text": page.raw_text[:1200],
                    "truncated": len(page.raw_text) > 1200,
                    "page_url": f"/api/reports/{report.id}/file#page={page.page_number}",
                }
            )
        # Whitespace-normalised excerpts are explicitly separate from immutable raw text.
        text = " ".join(page.raw_text.split())
        for match in BASIS.finditer(text):
            if len(basis) >= 6:
                break
            basis.append(
                {
                    "page": page.page_number,
                    "excerpt": text[max(0, match.start() - 80) : match.end() + 360],
                    "page_url": f"/api/reports/{report.id}/file#page={page.page_number}",
                }
            )
    role = (
        "supporting_document"
        if SUPPLEMENT.search(report.title + " " + report.source_url)
        else "primary_report_candidate"
    )
    warnings = []
    if role == "supporting_document":
        warnings.append("supporting_document_not_full_company_report")
    if index.quality.get("coverage") != "complete_extracted_text":
        warnings.append("some_pages_have_text_gaps")
    if report.detected_year is None and report.reporting_year is None:
        warnings.append("document_year_not_established_in_metadata")
    if not report.period_start or not report.period_end:
        warnings.append("reporting_period_not_established_in_metadata")
    if report.title.strip().lower() in {"view (pdf)", "download", "download (pdf)"} or (
        report.title.lower().startswith(("download download", "https://"))
    ):
        warnings.append("discovery_link_label_is_not_a_verified_report_title")
    file_check = "not_checked"
    if verify_file:
        root = settings.reports_root.resolve()
        path = (root / (report.storage_key or "")).resolve()
        try:
            if not path.is_relative_to(root) or not path.is_file():
                file_check = "missing_or_unsafe_path"
            else:
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                file_check = (
                    "matched" if digest == report.content_sha256 else "mismatch"
                )
        except OSError:
            file_check = "unreadable"
        if file_check != "matched":
            warnings.append("source_file_not_verified")
    return {
        "inspection_version": VERSION,
        "report_id": str(report.id),
        "company_id": str(company.id),
        "company": company.company_name,
        "registry_name_found_in_opening_pages": company.company_name.casefold()
        in " ".join(" ".join(p.raw_text.split()) for p in pages).casefold(),
        "identity_check_meaning": "Literal registry-name match only; not verification of corporate boundary or identity. Brand abbreviations may not match.",
        "title": report.title,
        "document_role": role,
        "document_role_method": "discovery_title_and_url_heuristic_not_validation",
        "source_url": report.source_url,
        "report_sha256": report.content_sha256,
        "file_checksum_check": file_check,
        "requested_year": report.requested_year,
        "detected_year": report.detected_year,
        "reporting_year": report.reporting_year,
        "period_start": report.period_start.isoformat()
        if report.period_start
        else None,
        "period_end": report.period_end.isoformat() if report.period_end else None,
        "year_meaning": "Requested year is a crawl filter; detected/report label is not the year of every observation. Read the cited period and table headings.",
        "pages_inspected": [p.page_number for p in pages],
        "opening_pages": opening,
        "period_and_boundary_excerpts": basis,
        "extraction_coverage": index.quality.get("coverage"),
        "warnings": warnings,
        "metrics_validated": False,
        "meaning": "Automated source inspection, not expert review. Excerpts are search aids, not resolved reporting periods or boundaries. No report metadata or observations were changed.",
    }
