"""Explicit, auditable official-source registration; never validates metric values.

A curator can resolve title-year/publication-year ambiguity without changing the
automatic crawler's exact-year policy. Downloads still use the normal robots,
redirect, domain, signature and size checks. Existing evidence is never deleted.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import unquote
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Company, Report, ReportDiscoveryRun
from app.discovery.crawler import SPECIALISED_FINANCING, EXCLUDED
from app.discovery.http import canonical_url
from app.discovery.service import policy_for


class CuratedSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: UUID
    requested_year: int = Field(ge=2000, le=2100)
    detected_year: int = Field(ge=2000, le=2100)
    title: str = Field(min_length=8, max_length=1000)
    report_type: Literal[
        "annual", "integrated", "sustainability", "esg", "climate", "environmental"
    ]
    source_url: str
    discovered_from_url: str
    year_basis: str = Field(min_length=30)
    scope_basis: str = Field(min_length=30)
    reviewed_by: str = Field(min_length=3)
    reviewed_at: datetime

    @field_validator("source_url", "discovered_from_url")
    @classmethod
    def public_url(cls, value: str) -> str:
        return canonical_url(value)


def register_sources(
    path: Path, engine: Engine, settings: Settings
) -> list[dict[str, str]]:
    entries = [
        CuratedSource.model_validate(row) for row in json.loads(path.read_text())
    ]
    keys = [(r.company_id, r.requested_year) for r in entries]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate company/cycle in source manifest")
    results = []
    with Session(engine) as session, session.begin():
        for entry in entries:
            company = session.get(Company, entry.company_id)
            if company is None:
                raise ValueError("Source company does not exist")
            policy = policy_for(company, settings)
            linked_policy = policy.endorse_document(
                entry.source_url, entry.discovered_from_url
            )
            if not policy.owns(entry.discovered_from_url) or not (
                policy.owns(entry.source_url)
                or entry.source_url in linked_policy.document_urls
            ):
                raise ValueError(
                    "Source must be official or an exact reviewed publisher PDF linked by an official page"
                )
            label = unquote(entry.title + " " + entry.source_url)
            if SPECIALISED_FINANCING.search(label) or EXCLUDED.search(label):
                raise ValueError(
                    "Excluded document cannot be registered as a primary source"
                )
            evidence = entry.model_dump(mode="json")
            digest = hashlib.sha256(
                json.dumps(evidence, sort_keys=True).encode()
            ).hexdigest()
            existing = session.scalar(
                select(Report)
                .join(ReportDiscoveryRun)
                .where(
                    Report.company_id == entry.company_id,
                    Report.requested_year == entry.requested_year,
                    (ReportDiscoveryRun.selection_reason == f"curated-source:{digest}")
                    | Report.notes.endswith(f"Source review: {digest}"),
                )
                .order_by(Report.created_at, Report.id)
            )
            if existing:
                results.append(
                    {
                        "company": company.company_name,
                        "report_id": str(existing.id),
                        "status": "unchanged",
                    }
                )
                continue
            diagnostics: list[dict[str, object]] = [
                {
                    "code": "explicit_source_review",
                    "evidence": evidence,
                    "metric_validation": False,
                }
            ]
            if entry.source_url in linked_policy.document_urls:
                diagnostics.append(
                    {
                        "code": "official_document_link",
                        "policy": "exact-publisher-pdf-v1",
                        "url": entry.source_url,
                        "source_page": entry.discovered_from_url,
                        "evidence_method": "explicit_source_review",
                        "message": "Exact company-published PDF link recorded in source review; not a general CDN grant.",
                    }
                )
            run = ReportDiscoveryRun(
                company_id=entry.company_id,
                requested_year=entry.requested_year,
                status="discovered",
                policy_version="curated-official-source-v1",
                selection_reason=f"curated-source:{digest}",
                sources=[entry.discovered_from_url],
                diagnostics=diagnostics,
                finished_at=datetime.now(UTC),
                pages_visited=0,
                http_requests=0,
            )
            session.add(run)
            session.flush()
            report = Report(
                company_id=entry.company_id,
                discovery_run_id=run.id,
                requested_year=entry.requested_year,
                detected_year=entry.detected_year,
                reporting_year=None,
                title=entry.title,
                report_type=entry.report_type,
                source_url=entry.source_url,
                discovered_from_url=entry.discovered_from_url,
                url_sha256=hashlib.sha256(entry.source_url.encode()).hexdigest(),
                confidence=None,
                selection_reason=entry.year_basis + " " + entry.scope_basis,
                status="discovered",
                is_selected=True,
                source_policy="official",
                notes="Explicit source selection only; reporting periods and metric values require page evidence. Source review: "
                + digest,
            )
            session.add(report)
            session.flush()
            results.append(
                {
                    "company": company.company_name,
                    "report_id": str(report.id),
                    "status": "registered",
                }
            )
    return results
