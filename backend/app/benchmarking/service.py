"""Bulk ORM read adapter and explicit, idempotent snapshot persistence."""

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.benchmarking.contracts import (
    CompanyData,
    Definition,
    EvidenceData,
    PeerGroup,
    Scope2Method,
)
from app.benchmarking.engine import build
from app.db.models import (
    BenchmarkComponent,
    BenchmarkSnapshot,
    Company,
    MetricDefinition,
    MetricObservation,
    Target,
    Report,
    ValidationEvent,
)


def provenance(row: MetricObservation | Target, code: str) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "kind": "target" if isinstance(row, Target) else "observation",
        "metric": code,
        "company_id": str(row.company_id),
        "report_id": str(row.report_id),
        "document_chunk_id": str(row.document_chunk_id),
        "extraction_run_id": str(row.extraction_run_id)
        if row.extraction_run_id
        else None,
        "reporting_year": row.reporting_year,
        "source_url": row.source_url,
        "source_page": row.source_physical_page,
        "supporting_excerpt": row.supporting_excerpt,
        "extraction_method": row.extraction_method,
        "confidence": str(row.confidence) if row.confidence is not None else None,
        "validation_state": row.validation_state,
        "notes": row.notes,
    }


def calculate(
    session: Session,
    *,
    year: int,
    peer_group: PeerGroup = "sector",
    min_peers: int = 5,
    scope2_method: Scope2Method = "location_based",
    company_ids: list[UUID] | None = None,
    report_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    companies = list(
        session.scalars(
            select(Company)
            .where(
                Company.active.is_(True),
                *([Company.id.in_(company_ids)] if company_ids is not None else []),
            )
            .order_by(Company.id)
        )
    )
    ids = [c.id for c in companies]
    definitions = list(
        session.scalars(select(MetricDefinition).order_by(MetricDefinition.id))
    )
    definition_map = {d.id: d for d in definitions}
    reports = {
        r.id: r
        for r in session.scalars(select(Report).where(Report.company_id.in_(ids)))
    }
    events: dict[UUID, ValidationEvent] = {}
    for event in session.scalars(
        select(ValidationEvent)
        .where(
            ValidationEvent.metric_observation_id.in_(
                select(MetricObservation.id).where(
                    MetricObservation.company_id.in_(ids),
                    MetricObservation.reporting_year.in_([year, year - 1]),
                )
            )
            | ValidationEvent.target_id.in_(
                select(Target.id).where(
                    Target.company_id.in_(ids), Target.reporting_year == year
                )
            )
        )
        .order_by(ValidationEvent.created_at, ValidationEvent.id)
    ):
        subject = event.metric_observation_id or event.target_id
        if subject:
            events[subject] = event

    def audit(row: MetricObservation | Target) -> dict[str, Any]:
        report = reports[row.report_id]
        event = events.get(row.id)
        return {
            "report_title": report.title,
            "report_sha256": report.content_sha256,
            "source_policy": report.source_policy,
            "report_retrieved_at": report.retrieved_at.isoformat()
            if report.retrieved_at
            else None,
            "validation_audit_current": bool(
                event
                and event.new_state == "validated"
                and event.created_at >= row.updated_at
                and event.created_at >= report.updated_at
                and row.source_url in {report.source_url, report.final_url}
            ),
            "validation_event": {
                "id": str(event.id),
                "actor_type": event.actor_type,
                "actor_reference": event.actor_reference,
                "reason": event.reason,
                "created_at": event.created_at.isoformat(),
                "rule_code": event.rule_code,
                "rule_version": event.rule_version,
            }
            if event
            else None,
        }

    rows = session.scalars(
        select(MetricObservation)
        .where(
            MetricObservation.company_id.in_(ids),
            MetricObservation.reporting_year.in_([year, year - 1]),
            *(
                [MetricObservation.report_id.in_(report_ids)]
                if report_ids is not None
                else []
            ),
        )
        .order_by(MetricObservation.id)
    )
    evidence = []
    # Typed columns take precedence over supplementary context. A JSON value cannot
    # silently override the recorded reporting boundary, period, or Scope 2 method.
    columns = (
        "organisational_boundary",
        "consolidation_basis",
        "scope2_method",
        "scope3_categories",
        "coverage_description",
        "methodology_version",
        "intensity_denominator",
        "denominator_unit",
        "currency_code",
        "currency_basis",
    )
    for row in rows:
        context: dict[str, Any] = dict(row.comparison_context)
        context.update({key: getattr(row, key) for key in columns})
        context.update(
            {
                "reporting_year": row.reporting_year,
                "period_start": row.period_start.isoformat()
                if row.period_start
                else None,
                "period_end": row.period_end.isoformat() if row.period_end else None,
            }
        )
        alignment = context.get("revenue_alignment")
        if isinstance(alignment, dict):
            # A free-form URL/"validated" flag is not enough for a financial
            # denominator. Resolve its recorded official document and checksum.
            try:
                financial_report = reports.get(UUID(str(alignment.get("report_id"))))
            except ValueError:
                financial_report = None
            financial_event = events.get(row.id)
            verified = bool(
                financial_report
                and financial_report.company_id == row.company_id
                and financial_report.source_policy == "official"
                and financial_report.content_sha256
                and financial_report.content_sha256 == alignment.get("report_sha256")
                and alignment.get("source_url")
                in {financial_report.source_url, financial_report.final_url}
                and type(alignment.get("source_page")) is int
                and 1 <= alignment["source_page"] <= (financial_report.page_count or 0)
                and financial_event
                and financial_event.new_state == "validated"
                and financial_event.created_at >= financial_report.updated_at
            )
            # Never trust an input JSON value for this engine-computed flag.
            context["revenue_alignment"] = alignment | {"source_verified": verified}
        source = provenance(row, definition_map[row.metric_definition_id].metric_code)
        source.update(audit(row))
        source.update(
            {
                "raw_value": row.raw_value,
                "raw_unit": row.raw_unit,
                "normalised_value": str(row.normalised_value)
                if row.normalised_value is not None
                else None,
                "normalised_unit": row.normalised_unit,
                "normalisation_rule_version": row.normalisation_rule_version,
                "is_restated": row.is_restated,
                "supersedes_observation_id": str(row.supersedes_observation_id)
                if row.supersedes_observation_id
                else None,
                "compatibility_state": row.compatibility_state,
                "comparison_context": context,
            }
        )
        evidence.append(
            EvidenceData(
                str(row.id),
                str(row.company_id),
                str(row.metric_definition_id),
                row.reporting_year,
                row.validation_state,
                row.normalised_value,
                row.normalised_unit,
                row.raw_value,
                row.value_qualifier,
                row.compatibility_state,
                context,
                source,
                str(row.supersedes_observation_id)
                if row.supersedes_observation_id
                else None,
            )
        )
    target_rows = session.scalars(
        select(Target)
        .where(Target.company_id.in_(ids), Target.reporting_year == year)
        .where(*([Target.report_id.in_(report_ids)] if report_ids is not None else []))
        .order_by(Target.id)
    )
    targets = []
    for target in target_rows:
        targets.append(
            provenance(target, definition_map[target.metric_definition_id].metric_code)
            | audit(target)
            | {
                "target_year": target.target_year,
                "scope": target.scope,
                "boundary": target.organisational_boundary,
                "coverage": target.target_coverage,
                "target_raw_value": target.target_raw_value,
                "target_raw_unit": target.target_raw_unit,
            }
        )
    return build(
        [
            CompanyData(
                str(c.id),
                c.company_name,
                c.sector,
                c.country,
                c.region,
                c.industry,
                c.revenue,
                c.revenue_year,
                c.reporting_currency,
            )
            for c in companies
        ],
        [
            Definition(
                str(d.id),
                d.metric_code,
                d.definition_version,
                d.canonical_unit,
                d.evidence_kind or "unknown",
                tuple(d.required_comparison_dimensions),
                d.score_eligibility,
                d.comparability_warning,
            )
            for d in definitions
        ],
        evidence,
        targets,
        year=year,
        peer_group=peer_group,
        min_peers=min_peers,
        scope2_method=scope2_method,
    )


def persist(session: Session, payload: dict[str, Any]) -> UUID:
    """Caller owns transaction. Same inputs/parameters reuse the existing snapshot."""
    snapshot_id = uuid4()
    parameters = {
        k: payload[k] for k in ("year", "peer_group", "minimum_peers", "scope2_method")
    }
    created = session.scalar(
        insert(BenchmarkSnapshot)
        .values(
            id=snapshot_id,
            reporting_year=payload["year"],
            methodology_version=payload["methodology_version"],
            input_sha256=payload["input_sha256"],
            parameters=parameters,
            results=payload | {"persistence": "stored_snapshot"},
        )
        .on_conflict_do_nothing(index_elements=["input_sha256"])
        .returning(BenchmarkSnapshot.id)
    )
    if created is None:
        existing = session.scalar(
            select(BenchmarkSnapshot.id).where(
                BenchmarkSnapshot.input_sha256 == payload["input_sha256"]
            )
        )
        assert existing is not None
        return existing
    for company in payload["items"]:
        for component in company["score"]["components"]:
            session.add(
                BenchmarkComponent(
                    snapshot_id=snapshot_id,
                    company_id=UUID(company["company_id"]),
                    component=component["component"],
                    score=Decimal(component["score"])
                    if component["score"] is not None
                    else None,
                    weight=Decimal(component["weight"]),
                    reason=component["reason"],
                    formula=component["formula"],
                    evidence=component["provenance"],
                )
            )
    session.flush()
    return snapshot_id


def sector_summary(payload: dict[str, Any], sector: str) -> dict[str, Any]:
    items = [c for c in payload["items"] if c["sector"].casefold() == sector.casefold()]
    cohorts: dict[tuple[str, str], dict[str, Any]] = {}
    for company in items:
        for code, metric in company["metrics"].items():
            key = metric["cohort_key"]
            if key is not None:
                cohorts[code, key] = {
                    "metric": code,
                    "cohort_key": key,
                    "comparison_dimensions": metric["comparison_dimensions"],
                    "unit": metric["unit"],
                    "sample_size": metric["sector_sample_size"],
                    "median": metric["sector_median"],
                    "reason": None
                    if metric["sector_median"] is not None
                    else "insufficient_comparable_peers",
                }
    return {
        "sector": items[0]["sector"] if items else sector,
        "year": payload["year"],
        "methodology_version": payload["methodology_version"],
        "label": payload["label"],
        "minimum_peers": payload["minimum_peers"],
        "companies_total": len(items),
        "companies_with_score": sum(c["score"]["value"] is not None for c in items),
        "cohorts": [cohorts[k] for k in sorted(cohorts)],
        "outliers": [
            {
                "company_id": c["company_id"],
                "metric": code,
                "value": m["value"],
                "unit": m["unit"],
                "flags": m["flags"],
                "sample_size": m["peer_sample_size"],
                "cohort_key": m["cohort_key"],
            }
            for c in items
            for code, m in c["metrics"].items()
            if m["flags"]
        ],
        "disclosure_gaps": [
            {"company_id": c["company_id"], "gaps": c["disclosure_gaps"]}
            for c in items
            if c["disclosure_gaps"]
        ],
        "target_flags": [
            {"company_id": c["company_id"], **flag}
            for c in items
            for flag in c["target_flags"]
        ],
        "notice": "Separate comparable cohorts, never a pooled median across units/boundaries. Extremes describe numeric position, not moral merit.",
    }
