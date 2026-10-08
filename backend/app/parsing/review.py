"""Audited page-level visual reviews; parser output is immutable and never erased."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import DocumentPage, ExtractionRun, Report

VERSION = "parse-page-review-v1"


class PageReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_number: int = Field(ge=1)
    disposition: Literal["decorative_no_metric_data", "requires_text_recovery"]
    reason: str = Field(min_length=30)


class ParseReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_id: UUID
    parse_run_id: UUID
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_by: str = Field(min_length=3)
    pages: list[PageReview] = Field(min_length=1)


def save_review(engine: Engine, manifest: Path) -> dict[str, str]:
    review = ParseReview.model_validate_json(manifest.read_text())
    page_numbers = [p.page_number for p in review.pages]
    if len(page_numbers) != len(set(page_numbers)):
        raise ValueError("Duplicate page review")
    payload = review.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with Session(engine) as session, session.begin():
        report = session.get(Report, review.report_id)
        parsed = session.get(ExtractionRun, review.parse_run_id)
        if (
            report is None
            or parsed is None
            or parsed.report_id != report.id
            or parsed.stage != "parsing"
            or parsed.status != "succeeded"
            or parsed.input_sha256 != review.document_sha256
            or report.content_sha256 != review.document_sha256
        ):
            raise ValueError(
                "Review must match a successful parse and exact downloaded PDF checksum"
            )
        pages = list(
            session.scalars(
                select(DocumentPage).where(
                    DocumentPage.parse_run_id == parsed.id,
                    DocumentPage.page_number.in_(page_numbers),
                    DocumentPage.status == "needs_ocr",
                )
            )
        )
        if len(pages) != len(page_numbers):
            raise ValueError(
                "Only existing needs_ocr pages can receive a visual disposition"
            )
        key = VERSION + ":" + digest
        old = session.scalar(
            select(ExtractionRun).where(ExtractionRun.idempotency_key == key)
        )
        if old:
            return {"status": "unchanged", "review_run_id": str(old.id)}
        now = datetime.now(UTC)
        run = ExtractionRun(
            report_id=report.id,
            parent_run_id=parsed.id,
            stage="quality",
            status="succeeded",
            idempotency_key=key,
            input_sha256=review.document_sha256,
            schema_version=VERSION,
            code_version=VERSION,
            parameters=payload,
            output_summary={
                "page_reviews": payload["pages"],
                "metric_validation": False,
                "ocr_performed": False,
                "actor": review.reviewed_by,
            },
            started_at=now,
            finished_at=now,
        )
        session.add(run)
        session.flush()
        return {"status": "recorded", "review_run_id": str(run.id)}


def reviewed_decorative_pages(
    session: Session, report_id: UUID, parse_id: UUID, checksum: str
) -> dict[int, str]:
    decisions = {}
    # Later reviews supersede earlier ones for the same exact page/parse/hash.
    for run in session.scalars(
        select(ExtractionRun)
        .where(
            ExtractionRun.report_id == report_id,
            ExtractionRun.parent_run_id == parse_id,
            ExtractionRun.input_sha256 == checksum,
            ExtractionRun.code_version == VERSION,
            ExtractionRun.stage == "quality",
            ExtractionRun.status == "succeeded",
        )
        .order_by(ExtractionRun.created_at, ExtractionRun.id)
    ):
        summary: dict[str, Any] = run.output_summary or {}
        for page in summary.get("page_reviews", []):
            decisions[int(page["page_number"])] = (
                str(run.id)
                if page["disposition"] == "decorative_no_metric_data"
                else None
            )
    return {page: identifier for page, identifier in decisions.items() if identifier}
