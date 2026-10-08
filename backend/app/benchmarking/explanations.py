"""Versioned, deterministic peer gaps. No language model or external requests.

Numeric comparisons use the benchmark engine's exact cohorts and statistics.
Reporting coverage is a separate evidence-availability statistic, not a pooled
comparison of quantities. Unknown evidence is never labelled nondisclosure.
"""

import csv
import hashlib
import io
import json
import re
from decimal import Decimal as D, ROUND_HALF_EVEN, localcontext
from typing import Any

from app.benchmarking.engine import canonical, number, source_verified

VERSION = "peer-gap-v1"
COMMON_THRESHOLD = D(50)
NUMERIC = (
    (
        "emissions_trajectory",
        "derived_yoy_emissions_change",
        "Emissions trajectory",
        "lower",
    ),
    (
        "renewable_energy",
        "derived_renewable_energy_adoption",
        "Renewable energy",
        "higher",
    ),
    (
        "disclosure_completeness",
        "derived_disclosure_completeness",
        "Disclosure completeness",
        "higher",
    ),
    (None, "renewable_electricity_percent", "Renewable electricity", "higher"),
)
COMMON = (
    ("scope3_supplier_engagement", "Supplier engagement", True),
    ("water_consumption", "Water consumption", False),
    ("recycled_or_diverted_percent", "Waste diversion", False),
)


def usable(metric: dict[str, Any]) -> bool:
    return (
        metric.get("value") is not None
        and metric.get("eligibility_reason", metric.get("reason")) is None
    )


def sources(
    company: dict[str, Any], evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        s
        | {"company_id": company["company_id"], "company_name": company["company_name"]}
        for s in evidence
    ]


def base(code: str, label: str, kind: str) -> dict[str, Any]:
    return dict(
        metric=code,
        label=label,
        kind=kind,
        company_value=None,
        unit=None,
        sector_median=None,
        percentile=None,
        difference=None,
        difference_unit=None,
        value_relation=None,
        preferred_direction=None,
        effect="unavailable",
        status="missing_metric",
        reason="missing_validated_evidence",
        score_weight="0",
        component_score=None,
        weighted_points=None,
        provenance=[],
        peer_provenance=[],
        peer_members=[],
        peer_sample_size=0,
        cohort_key=None,
        completeness={},
        peer_rate=None,
        peer_rate_kind=None,
    )


def numeric_factor(
    company: dict[str, Any],
    sector: list[dict[str, Any]],
    minimum: int,
    component: str | None,
    code: str,
    label: str,
    direction: str,
) -> dict[str, Any]:
    metric = company["metrics"].get(code, {})
    factor = base(code, label, "score_component" if component else "context_metric")
    factor.update(
        company_value=metric.get("value"),
        unit=metric.get("unit"),
        preferred_direction=direction,
        provenance=sources(company, metric.get("provenance", [])),
        cohort_key=metric.get("cohort_key"),
    )
    parts = [p for p in company["score"]["components"] if p["component"] == component]
    part = parts[0] if parts else None
    if part:
        factor.update(score_weight=part["weight"], component_score=part["score"])
        coverage = D(company["score"]["coverage_percent"] or "0") / 100
        if (
            company["score"]["value"] is not None
            and part["score"] is not None
            and coverage > 0
        ):
            factor["weighted_points"] = number(
                D(part["score"]) * D(part["weight"]) / coverage
            )
    peers = [
        p
        for p in sector
        if usable(p["metrics"].get(code, {}))
        and metric.get("cohort_key")
        and p["metrics"][code]["cohort_key"] == metric["cohort_key"]
    ]
    n = len(peers)
    context = metric.get("comparison_dimensions", {})
    factor["completeness"] = dict(
        company_complete=usable(metric),
        assessed_inputs=context.get("assessed"),
        required_inputs=context.get("total"),
        comparable_companies=n,
        sector_companies=len(sector),
        comparable_coverage_percent=number(D(n) * 100 / len(sector)),
    )
    factor["peer_sample_size"] = n
    factor["peer_members"] = [
        dict(
            company_id=p["company_id"],
            company_name=p["company_name"],
            value=p["metrics"][code]["value"],
        )
        for p in peers
    ]
    factor["peer_provenance"] = [
        s for p in peers for s in sources(p, p["metrics"][code]["provenance"])
    ]
    reason = metric.get("eligibility_reason", "missing_validated_evidence") or (
        part.get("reason") if part else None
    )
    if reason or metric.get("value") is None:
        missing = (
            reason
            in {None, "missing_validated_evidence", "requires_two_comparable_years"}
            and metric.get("value") is None
        )
        factor.update(
            status="missing_metric" if missing else "not_comparable",
            reason=reason or "missing_validated_evidence",
            effect="missing_evidence" if missing else "not_comparable",
        )
        return factor
    if (
        n < minimum
        or metric.get("sector_median") is None
        or metric.get("sector_percentile") is None
    ):
        factor.update(
            status="insufficient_peers",
            reason="insufficient_comparable_peers",
            effect="insufficient_peers",
        )
        return factor
    difference = D(metric["value"]) - D(metric["sector_median"])
    relation = "above" if difference > 0 else "below" if difference < 0 else "at"
    favourable = difference * (1 if direction == "higher" else -1)
    factor.update(
        status="comparable",
        reason=None,
        sector_median=metric["sector_median"],
        percentile=metric["sector_percentile"],
        difference=number(difference),
        difference_unit=(
            "percentage_points" if metric["unit"] == "%" else metric["unit"]
        ),
        value_relation=relation,
        effect=(
            "above_peer_median"
            if favourable > 0
            else "below_peer_median" if favourable < 0 else "at_peer_median"
        ),
    )
    return factor


def reporting_state(
    company: dict[str, Any], code: str, boolean: bool
) -> tuple[str, dict[str, Any]]:
    record = (
        company.get("context_indicators", {}).get(code, {})
        if boolean
        else company["metrics"].get(code, {})
    )
    if usable(record):
        # False programme status is still an explicit disclosure. Scope 3's
        # availability flag is different: false is a reviewed absence claim.
        return (
            "reported"
            if code != "scope3_available" or record["value"]
            else "not_reported"
        ), record
    return "unknown", record


def coverage_factor(
    company: dict[str, Any],
    sector: list[dict[str, Any]],
    minimum: int,
    code: str,
    label: str,
    boolean: bool,
    prevalence: bool = False,
) -> dict[str, Any]:
    state, own = reporting_state(company, code, boolean)
    factor = base(
        code, label, "peer_prevalence" if prevalence else "disclosure_coverage"
    )
    factor.update(
        company_value=(
            str(own["value"]).lower()
            if boolean and state != "unknown"
            else own.get("value")
        ),
        company_state=state,
        provenance=sources(company, own.get("provenance", [])),
    )
    others = [p for p in sector if p["company_id"] != company["company_id"]]
    assessed = [(p, *reporting_state(p, code, boolean)) for p in others]
    known = [(p, s, m) for p, s, m in assessed if s != "unknown"]
    # Presence rates may span boundaries, not metric versions. Prevalence of an
    # actual governance practice additionally requires a matching context.
    versions = {canonical(m.get("definition_ids", [])) for _, _, m in known}
    if state != "unknown":
        versions.add(canonical(own.get("definition_ids", [])))
    mixed = len(versions) > 1
    if prevalence:
        known = [
            (p, s, m)
            for p, s, m in known
            if own.get("cohort_key") and m.get("cohort_key") == own["cohort_key"]
        ]
    numerator = sum(
        bool(m["value"]) if prevalence else s == "reported" for _, s, m in known
    )
    denominator = len(known) if prevalence else len(others)
    factor.update(
        peer_sample_size=len(known),
        peer_rate_kind=(
            "affirmative_prevalence" if prevalence else "verified_reporting_coverage"
        ),
        completeness=dict(
            company_complete=state != "unknown",
            sector_companies=len(sector),
            peer_companies=len(others),
            assessed_peers=len(known),
            unknown_peers=len(others) - len(known),
            reported_peers=numerator,
            denominator=denominator,
            review_coverage_percent=(
                number(D(len(known)) * 100 / len(others)) if others else None
            ),
        ),
        peer_members=[
            dict(
                company_id=p["company_id"],
                company_name=p["company_name"],
                value=str(m["value"]).lower(),
                state=s,
            )
            for p, s, m in known
        ],
        peer_provenance=[
            source
            for p, _, m in known
            for source in sources(p, m.get("provenance", []))
        ],
    )
    if mixed:
        factor.update(
            status="not_comparable",
            effect="not_comparable",
            reason="conflicting_metric_definitions",
        )
    elif prevalence and state == "unknown":
        factor.update(
            status="missing_metric",
            effect="missing_evidence",
            reason=own.get("reason") or "missing_validated_evidence",
        )
    elif len(known) < minimum:
        factor.update(
            status="insufficient_peers",
            effect="insufficient_peers",
            reason="insufficient_assessed_peers",
        )
    else:
        factor.update(
            peer_rate=number(D(numerator) * 100 / denominator),
            status="available",
            reason=None,
            effect=(
                "context_only"
                if prevalence
                else (
                    "disclosure_gap"
                    if state == "not_reported"
                    else "review_gap" if state == "unknown" else "reported"
                )
            ),
        )
    return factor


def explain(payload: dict[str, Any], company_id: str) -> dict[str, Any]:
    with localcontext() as context:
        context.prec = 64
        context.rounding = ROUND_HALF_EVEN
        return _explain(payload, company_id)


def _explain(payload: dict[str, Any], company_id: str) -> dict[str, Any]:
    company = next((c for c in payload["items"] if c["company_id"] == company_id), None)
    if company is None:
        raise KeyError(company_id)
    sector = [
        c
        for c in payload["items"]
        if c["sector"].casefold() == company["sector"].casefold()
    ]
    minimum = payload["minimum_peers"]
    factors = [numeric_factor(company, sector, minimum, *spec) for spec in NUMERIC]
    factors += [
        coverage_factor(
            company, sector, minimum, "scope3_available", "Scope 3 reporting", True
        ),
        coverage_factor(
            company,
            sector,
            minimum,
            "board_sustainability_oversight",
            "Board sustainability oversight",
            True,
            True,
        ),
    ]
    target = base("net_zero_target_year", "Net-zero target", "context_only")
    target_sources = [
        t for t in company["targets"] if t.get("metric") == "net_zero_target_year"
    ]
    years = {
        t["target_year"]
        for t in target_sources
        if t.get("validation_state") == "validated" and source_verified(t)
    }
    target.update(
        status="not_comparable",
        reason="commitment_not_performance",
        effect="context_only",
        company_value=str(next(iter(years))) if len(years) == 1 else None,
        unit="year",
        provenance=sources(company, target_sources),
        completeness={"company_complete": len(years) == 1},
    )
    factors.append(target)
    opportunities = [
        coverage_factor(company, sector, minimum, code, label, boolean)
        for code, label, boolean in COMMON
    ]
    for factor in opportunities:
        factor["common_gap"] = (
            factor["company_state"] in {"unknown", "not_reported"}
            and factor["peer_rate"] is not None
            and D(factor["peer_rate"]) >= COMMON_THRESHOLD
        )
    result = dict(
        version=VERSION,
        title="Why this position?",
        company_id=company_id,
        company_name=company["company_name"],
        sector=company["sector"],
        year=payload["year"],
        input_sha256=payload["input_sha256"],
        methodology_version=payload["methodology_version"],
        label=payload["label"],
        minimum_peers=minimum,
        peer_group="sector",
        score=company["score"],
        factors=factors,
        disclosure_opportunities=opportunities,
        common_threshold_percent=str(COMMON_THRESHOLD),
        notice="Deterministic comparisons, not causal rank attribution. Live composite ranking remains disabled. Numeric cohorts include the subject; reporting/prevalence peers exclude it. Unknown evidence is not nondisclosure. Reporting coverage is a verified lower bound across the sector, not a comparison of metric quantities.",
    )
    result["explanation_sha256"] = hashlib.sha256(
        canonical(result).encode()
    ).hexdigest()
    return result


def csv_export(explanation: dict[str, Any]) -> str:
    """One factor per row, full provenance in JSON cells; spreadsheet-safe text."""
    stream = io.StringIO(newline="")
    columns = [
        "company_id",
        "company_name",
        "sector",
        "year",
        "version",
        "input_sha256",
        "explanation_sha256",
        "section",
        "metric",
        "label",
        "kind",
        "company_value",
        "unit",
        "sector_median",
        "percentile",
        "difference",
        "difference_unit",
        "preferred_direction",
        "value_relation",
        "effect",
        "status",
        "reason",
        "score_weight",
        "component_score",
        "weighted_points",
        "peer_sample_size",
        "peer_rate",
        "peer_rate_kind",
        "company_state",
        "common_gap",
        "cohort_key",
        "completeness",
        "peer_members",
        "provenance",
        "peer_provenance",
        "notice",
    ]
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for section in ("factors", "disclosure_opportunities"):
        for factor in explanation[section]:
            record = {k: explanation.get(k) for k in columns if k in explanation}
            record.update(factor)
            record["section"] = section
            cells = {}
            for key in columns:
                value = record.get(key)
                text = (
                    json.dumps(value, sort_keys=True, ensure_ascii=False)
                    if isinstance(value, (list, dict))
                    else "" if value is None else str(value)
                )
                # Preserve exact raw provenance inside quoted JSON; prevent CSV formulas.
                numeric = key in {
                    "company_value",
                    "sector_median",
                    "difference",
                    "percentile",
                    "component_score",
                    "weighted_points",
                } and re.fullmatch(r"-?\d+(?:\.\d+)?", text)
                unsafe = text.lstrip().startswith(
                    ("=", "+", "-", "@")
                ) or text.startswith(("\t", "\r"))
                cells[key] = "'" + text if unsafe and not numeric else text
            writer.writerow(cells)
    return stream.getvalue()
