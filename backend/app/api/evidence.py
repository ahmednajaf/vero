"""Source library and explicit metric extraction, independent of ranking eligibility.

Reported observations are not approved by displaying them. Download counts exclude
discovery candidates; retained PDFs are checksum-checked before they are served.
"""

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.companies import Database
from app.db.models import (
    Company,
    MetricDefinition,
    MetricObservation,
    Report,
    ValidationEvent,
)
from app.discovery.crawler import SPECIALISED_FINANCING
from app.db.session import get_engine
from app.extraction.service import extract_metric
from app.llm.contracts import ExtractionError
from app.llm.openai import OpenAIStructuredExtractor
from app.catalogue.seed import load_catalogue

router = APIRouter(prefix="/api", tags=["evidence library"])


class MetricExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    metric: str = Field(min_length=1, max_length=100)
    observation_year: int = Field(ge=1900, le=2100)


@router.post("/reports/{report_id}/extract-metric")
async def extract_report_metric(
    report_id: UUID, body: MetricExtractionRequest, request: Request
) -> dict[str, Any]:
    """One selected metric, one page-aware passage; cached, never auto-expanded."""
    metric = next(
        (m for m in load_catalogue().metrics if m.canonical_id == body.metric), None
    )
    if metric is None or metric.evidence_kind == "target":
        raise HTTPException(422, detail={"code": "unsupported_extraction_metric"})
    engine, settings = get_engine(request), request.app.state.settings
    try:
        result = await extract_metric(
            engine,
            report_id,
            body.metric,
            body.observation_year,
            settings,
            OpenAIStructuredExtractor(settings, engine),
            top_k=1,
            resume_calls=True,
        )
    except ExtractionError as exc:
        raise HTTPException(409, detail={"code": exc.code}) from None
    except ValueError:
        raise HTTPException(
            422, detail={"code": "report_not_ready_for_extraction"}
        ) from None
    summary = result.get("summary", {})
    errors = list(
        dict.fromkeys(
            c["error_code"] for c in summary.get("calls", []) if c.get("error_code")
        )
    )
    if errors:
        raise HTTPException(409, detail={"code": errors[0]})
    return {
        "report_id": str(report_id),
        "metric": body.metric,
        "year": body.observation_year,
        "status": result["status"],
        "run_id": result.get("run_id"),
        "observations": summary.get("observation_count", 0),
        "states": summary.get("persisted_states", {}),
        "warnings": sorted(
            {
                flag
                for a in summary.get("assessments", [])
                for flag in a.get("quality_flags", [])
            }
        ),
        "absence_established": False,
    }


@router.get("/library")
def library(session: Database) -> dict[str, Any]:
    companies = session.scalars(
        select(Company).where(Company.active).order_by(Company.company_name)
    ).all()
    ids = [c.id for c in companies]
    reports = session.scalars(
        select(Report).where(Report.company_id.in_(ids), Report.status == "downloaded")
    ).all()
    observations = session.execute(
        select(
            MetricObservation.company_id,
            MetricObservation.validation_state,
            func.count(),
        )
        .where(MetricObservation.company_id.in_(ids))
        .group_by(MetricObservation.company_id, MetricObservation.validation_state)
    ).all()
    report_counts = Counter(r.company_id for r in reports)
    counts: dict[UUID, Counter[str]] = {c.id: Counter() for c in companies}
    for company_id, state, count in observations:
        counts[company_id][state] = count
    states = sum(counts.values(), Counter())
    return {
        "companies_total": len(companies),
        "pilot_companies": sum(
            Path(c.source_file or "").name == "company_universe_200.csv"
            for c in companies
        ),
        "reports_downloaded": len(reports),
        "observations_total": sum(states.values()),
        "observation_states": dict(states),
        "items": [
            {
                "company_id": str(c.id),
                "company_name": c.company_name,
                "reports_downloaded": report_counts[c.id],
                "observations": sum(counts[c.id].values()),
                "observation_states": dict(counts[c.id]),
            }
            for c in companies
        ],
    }


@router.get("/companies/{company_id}/evidence")
def company_evidence(company_id: UUID, session: Database) -> dict[str, Any]:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    reports = session.scalars(
        select(Report)
        .where(Report.company_id == company_id, Report.status == "downloaded")
        .order_by(Report.reporting_year.desc(), Report.created_at.desc())
    ).all()
    rows = session.execute(
        select(MetricObservation, MetricDefinition, Report)
        .join(
            MetricDefinition,
            MetricObservation.metric_definition_id == MetricDefinition.id,
        )
        .join(Report, MetricObservation.report_id == Report.id)
        .where(MetricObservation.company_id == company_id)
        .order_by(
            MetricObservation.reporting_year.desc(),
            MetricDefinition.metric_code,
            MetricObservation.created_at.desc(),
            MetricObservation.id.desc(),
        )
    ).all()
    events = session.scalars(
        select(ValidationEvent)
        .where(ValidationEvent.metric_observation_id.in_([o.id for o, _, _ in rows]))
        .order_by(ValidationEvent.created_at.desc(), ValidationEvent.id.desc())
    ).all()
    latest: dict[UUID, ValidationEvent] = {}
    for audit_event in events:
        if audit_event.metric_observation_id is not None:
            latest.setdefault(audit_event.metric_observation_id, audit_event)
    observations = []
    for observation, definition, report in rows:
        event = latest.get(observation.id)
        observations.append(
            {
                "id": str(observation.id),
                "metric": definition.metric_code,
                "name": definition.name,
                "company_id": str(company_id),
                "company_name": company.company_name,
                "report_id": str(report.id),
                "report_title": (
                    report.title
                    if report.title.lower()
                    not in {"download", "view (pdf)", "download the report"}
                    else unquote(urlsplit(report.source_url).path.rsplit("/", 1)[-1])
                ),
                "report_sha256": report.content_sha256,
                "reporting_year": observation.reporting_year,
                "report_year": report.reporting_year,
                "source_url": observation.source_url,
                "source_page": observation.source_physical_page,
                "supporting_excerpt": observation.supporting_excerpt,
                "raw_value": observation.raw_value,
                "raw_unit": observation.raw_unit,
                "normalised_value": (
                    str(observation.normalised_value)
                    if observation.normalised_value is not None
                    else None
                ),
                "normalised_unit": observation.normalised_unit,
                "validation_state": observation.validation_state,
                "compatibility_state": observation.compatibility_state,
                "validation_audit_current": event is not None
                and event.new_state == observation.validation_state,
                "validation_event": (
                    {"actor_reference": event.actor_reference, "reason": event.reason}
                    if event
                    else None
                ),
                "extraction_method": observation.extraction_method,
                "confidence": (
                    str(observation.confidence)
                    if observation.confidence is not None
                    else None
                ),
                "source_policy": report.source_policy,
                "notes": observation.notes,
                "boundary": observation.organisational_boundary,
                "local_report_url": (
                    f"/api/reports/{report.id}/file"
                    if report.status == "downloaded"
                    else None
                ),
            }
        )
    return {
        "company_id": str(company_id),
        "observations": observations,
        "reports": [
            {
                "id": str(r.id),
                "title": r.title,
                "reporting_year": r.reporting_year,
                "detected_year": r.detected_year,
                "requested_year": r.requested_year,
                "source_url": r.source_url,
                "sha256": r.content_sha256,
                "pages": r.page_count,
                "parse_status": r.parse_status,
                "source_policy": r.source_policy,
                "primary_source_exclusion": (
                    "specialised_financing_disclosure"
                    if SPECIALISED_FINANCING.search(
                        unquote(f"{r.title} {r.source_url}")
                    )
                    else None
                ),
                "local_url": f"/api/reports/{r.id}/file",
            }
            for r in reports
        ],
    }


@router.get("/reports/{report_id}/file")
def report_file(report_id: UUID, request: Request, session: Database) -> FileResponse:
    report = session.get(Report, report_id)
    if (
        report is None
        or report.status != "downloaded"
        or not report.storage_key
        or not report.content_sha256
    ):
        raise HTTPException(404, "Downloaded report not available")
    config = request.app.state.settings
    root = config.reports_root.resolve()
    path = (root / report.storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Report file not available")
    if path.stat().st_size > config.discovery_max_download_mb * 1024 * 1024:
        raise HTTPException(413, "Report exceeds configured file limit")
    with path.open("rb") as file:
        if file.read(5) != b"%PDF-":
            raise HTTPException(409, "Stored document is not a PDF")
        file.seek(0)
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    if digest != report.content_sha256:
        raise HTTPException(409, "Report checksum mismatch; file withheld")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"report-{report.id}.pdf",
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )
