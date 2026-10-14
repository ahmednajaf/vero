"""Pure calculations. Exact Decimal arithmetic until API serialization.

No inference of comparison dimensions: absent context is a blocking reason.
The catalogue's required dimensions are evaluated, not an opaque group key.
"""

import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from statistics import median
from app.extraction.units import convert
from typing import Any, Iterable

from app.benchmarking.contracts import (
    CompanyData,
    Definition,
    DISCLOSURES,
    EvidenceData,
    LABEL,
    Measure,
    PeerGroup,
    Scope2Method,
    VERSION,
)

D = Decimal


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def number(value: Decimal | None) -> str | None:
    # API decimals are strings, avoiding loss for large emissions/revenue amounts.
    return (
        str(value.quantize(D("0.000001")))
        if value is not None and value.is_finite()
        else None
    )


def percentile(
    value: Decimal, values: list[Decimal], minimum: int = 5
) -> Decimal | None:
    """Ascending midrank percentile, including the subject; all ties => 50."""
    if minimum < 5:
        raise ValueError("At least five comparable companies are required")
    if len(values) < minimum or value not in values:
        return None
    below = sum(v < value for v in values)
    equal = sum(v == value for v in values)
    return D(100) * (D(below) + D(equal - 1) / 2) / D(len(values) - 1)


def revenue_band(company: CompanyData, year: int) -> str | None:
    value = company.revenue
    if (
        value is None
        or not value.is_finite()
        or value <= 0
        or company.revenue_year != year
        or not company.currency
    ):
        return None
    band = (
        "under_1bn"
        if value < D("1e9")
        else (
            "1bn_to_10bn"
            if value < D("1e10")
            else "10bn_to_100bn" if value < D("1e11") else "100bn_plus"
        )
    )
    return f"{company.currency}:{year}:{band}"


def peer_key(company: CompanyData, group: PeerGroup, year: int) -> str | None:
    if group == "revenue_band":
        return revenue_band(company, year)
    value = getattr(company, group)
    return str(value).strip().casefold() or None


def signature(measure: Measure) -> str:
    return canonical([measure.definitions, measure.unit, measure.context])


def clean_context(
    evidence: EvidenceData, definition: Definition
) -> tuple[dict[str, Any], list[str]]:
    context = {key: evidence.context.get(key) for key in definition.required}
    context["reporting_year"] = evidence.year
    missing = [
        key
        for key, value in context.items()
        if value is None or value == "" or value == [] or value == {}
    ]
    return context, missing


def source_verified(provenance: dict[str, Any]) -> bool:
    return bool(
        provenance.get("source_url")
        and provenance.get("supporting_excerpt")
        and provenance.get("source_page")
        and provenance.get("report_sha256")
        and provenance.get("source_policy") == "official"
        and provenance.get("validation_audit_current") is True
    )


def resolve(
    code: str, rows: list[EvidenceData], definitions: dict[str, Definition]
) -> Measure:
    definitions_used = {e.definition_id for e in rows if e.state == "validated"}
    result = Measure(
        code, provenance=[e.provenance for e in sorted(rows, key=lambda e: e.id)]
    )
    approved = [e for e in rows if e.state == "validated"]
    if not approved:
        return result
    if len(definitions_used) != 1:
        result.reason = "conflicting_metric_definitions"
        return result
    definition = definitions[approved[0].definition_id]
    result.definitions = (f"{definition.code}:v{definition.version}:{definition.id}",)
    if definition.kind != "performance":
        result.reason = "context_only_not_performance"
        return result
    candidates: list[Measure] = []
    for row in approved:
        context, missing = clean_context(row, definition)
        comparison_unit = definition.unit or row.unit
        comparison_value = (convert(row.value, row.unit, comparison_unit)
                            if row.value is not None and row.unit and comparison_unit and row.unit != comparison_unit
                            else row.value)
        reason = None
        if not source_verified(row.provenance):
            reason = "source_or_validation_audit_missing"
        elif row.value is None or not row.value.is_finite():
            reason = "missing_finite_normalised_value"
        elif row.compatibility != "comparable":
            reason = "comparability_not_reviewed"
        elif row.qualifier != "exact":
            reason = "qualified_value_not_ranked"
        elif not row.unit or comparison_value is None:
            reason = "incompatible_unit_dimension"
        elif missing:
            reason = "missing_comparison_dimensions:" + ",".join(sorted(missing))
        elif "period_start" in context and not valid_period(context, row.year):
            reason = "invalid_or_mismatched_reporting_period"
        elif code.startswith("scope_2_") and context.get(
            "scope2_method"
        ) != code.removeprefix("scope_2_"):
            reason = "scope2_method_mismatch"
        elif (
            definition.unit == "%"
            and code != "yoy_emissions_change"
            and not D(0) <= comparison_value <= D(100)
        ):
            reason = "percent_out_of_range"
        elif code == "yoy_emissions_change" and comparison_value < -100:
            reason = "change_below_minus_100"
        elif definition.unit != "%" and comparison_value < 0:
            reason = "negative_performance_value"
        # Additional reviewed metadata is used only by revenue derivation.
        context_with_revenue = dict(context)
        if "revenue_alignment" in row.context:
            context_with_revenue["revenue_alignment"] = row.context["revenue_alignment"]
        candidates.append(
            Measure(
                code,
                comparison_value,
                comparison_unit,
                context_with_revenue,
                result.definitions,
                [row.provenance],
                reason,
            )
        )
    identities = {
        canonical(
            [m.value.normalize() if m.value is not None else None, m.unit, m.context]
        )
        for m in candidates
    }
    if len(identities) > 1:
        result.reason = "conflicting_validated_evidence"
        return result
    first = candidates[0]
    result.value, result.unit, result.context = first.value, first.unit, first.context
    result.reason = next((m.reason for m in candidates if m.reason), None)
    return result


def context_without(measure: Measure, keys: Iterable[str]) -> dict[str, Any]:
    return {
        key: value for key, value in measure.context.items() if key not in set(keys)
    }


def combine(scope1: Measure, scope2: Measure, method: Scope2Method) -> Measure:
    result = Measure(
        "derived_scope_1_2_total",
        unit="tCO2e",
        formula=f"scope_1_emissions + scope_2_{method}",
        provenance=scope1.provenance + scope2.provenance,
    )
    if not scope1.comparable or not scope2.comparable:
        result.reason = "requires_comparable_scope1_and_selected_scope2"
        return result
    common = set(scope1.context) & set(scope2.context) - {"revenue_alignment"}
    if (
        scope1.unit != "tCO2e"
        or scope2.unit != "tCO2e"
        or any(scope1.context[k] != scope2.context[k] for k in common)
    ):
        result.reason = "scope1_scope2_context_mismatch"
        return result
    assert scope1.value is not None and scope2.value is not None
    result.value = scope1.value + scope2.value
    result.context = {
        **scope1.context,
        **scope2.context,
        "included_scopes": [1, 2],
        "scope2_method": method,
    }
    # Never copy a denominator attestation for a different boundary.
    if scope1.context.get("revenue_alignment") != scope2.context.get(
        "revenue_alignment"
    ):
        result.context.pop("revenue_alignment", None)
    result.definitions = scope1.definitions + scope2.definitions
    result.reason = None
    return result


def reconcile_total(derived: Measure, reported: Measure) -> None:
    """An explicit like-for-like reported total must not contradict the sum."""
    if not derived.comparable or not reported.comparable:
        return
    common = (set(derived.context) & set(reported.context)) - {"revenue_alignment"}
    if (
        derived.unit == reported.unit
        and all(derived.context[k] == reported.context[k] for k in common)
        and derived.value != reported.value
    ):
        derived.reason = "reported_and_derived_total_conflict"
        derived.provenance.extend(reported.provenance)


def annual_period(context: dict[str, Any]) -> tuple[str, str] | None:
    try:
        start, end = (
            date.fromisoformat(context["period_start"]),
            date.fromisoformat(context["period_end"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if not 364 <= (end - start).days <= 366:
        return None
    return start.strftime("%m-%d"), end.strftime("%m-%d")


def valid_period(context: dict[str, Any], year: int) -> bool:
    try:
        start = date.fromisoformat(context["period_start"])
        end = date.fromisoformat(context["period_end"])
        return start <= end and end.year == year
    except (KeyError, ValueError, TypeError):
        return False


def yoy(current: Measure, prior: Measure) -> Measure:
    result = Measure(
        "derived_yoy_emissions_change",
        unit="%",
        formula="100 * (current_scope1_2 - prior_scope1_2) / prior_scope1_2",
        provenance=current.provenance + prior.provenance,
    )
    remove = {"reporting_year", "period_start", "period_end", "revenue_alignment"}
    if not current.comparable or not prior.comparable:
        result.reason = "requires_two_comparable_years"
    elif current.definitions != prior.definitions or context_without(
        current, remove
    ) != context_without(prior, remove):
        result.reason = "year_on_year_boundary_or_method_change"
    elif annual_period(current.context) is None or annual_period(
        current.context
    ) != annual_period(prior.context):
        result.reason = "non_matching_annual_periods"
    elif (
        date.fromisoformat(current.context["period_end"]).year
        != date.fromisoformat(prior.context["period_end"]).year + 1
    ):
        result.reason = "non_consecutive_periods"
    elif prior.value is None or prior.value <= 0:
        result.reason = "zero_or_invalid_prior_emissions"
    else:
        assert current.value is not None
        result.value = (current.value - prior.value) / prior.value * 100
        result.context = context_without(current, {"revenue_alignment"})
        result.context["comparison_metric"] = current.code
        result.definitions = current.definitions
        result.reason = None
    return result


def intensity(total: Measure, company: CompanyData, year: int) -> Measure:
    result = Measure(
        "derived_emissions_per_revenue",
        formula="scope1_2_tCO2e / (same-year consolidated revenue / 1000000)",
        provenance=list(total.provenance),
    )
    if not total.comparable or revenue_band(company, year) is None:
        result.reason = "requires_valid_same_year_revenue_and_emissions"
        return result
    alignment = total.context.get("revenue_alignment")
    required = {
        "validated",
        "value",
        "currency",
        "year",
        "period_start",
        "period_end",
        "organisational_boundary",
        "currency_basis",
        "unit_scale",
        "source_url",
        "source_page",
        "supporting_excerpt",
        "report_id",
        "report_sha256",
        "source_verified",
    }
    if (
        not isinstance(alignment, dict)
        or not required <= alignment.keys()
        or any(alignment[k] in (None, "") for k in required)
    ):
        result.reason = "revenue_boundary_period_and_source_not_reviewed"
        return result
    if (
        alignment["validated"] is not True
        or alignment["source_verified"] is not True
        or not decimal_equal(alignment["value"], company.revenue)
        or alignment["currency"] != company.currency
        or alignment["year"] != year
        or str(alignment["unit_scale"]) != "1"
        or any(
            alignment[k] != total.context.get(k)
            for k in ("period_start", "period_end", "organisational_boundary")
        )
    ):
        result.reason = "revenue_denominator_mismatch"
        return result
    assert company.revenue is not None and total.value is not None
    result.value = total.value * D(1000000) / company.revenue
    result.unit = f"tCO2e/million_{company.currency}"
    result.context = context_without(total, {"revenue_alignment"}) | {
        "denominator": "consolidated_revenue",
        "currency": company.currency,
        "currency_basis": alignment["currency_basis"],
        "denominator_scale": "1000000",
    }
    result.provenance.append({"kind": "reviewed_revenue", **alignment})
    result.definitions = total.definitions
    result.reason = None
    return result


def decimal_equal(raw: Any, value: Decimal | None) -> bool:
    try:
        return D(str(raw)).is_finite() and D(str(raw)) == value
    except ArithmeticError:
        return False


def disclosure(
    rows: list[EvidenceData], definitions: dict[str, Definition]
) -> tuple[Measure, list[dict[str, Any]]]:
    present, known = 0, 0
    sources: list[dict[str, Any]] = []
    definitions_used: list[str] = []
    entity_scopes: set[str] = set()
    gaps = []
    for code in DISCLOSURES:
        matches = [e for e in rows if definitions[e.definition_id].code == code]
        approved = [
            e
            for e in matches
            if e.state == "validated"
            and e.qualifier == "exact"
            and not clean_context(e, definitions[e.definition_id])[1]
            and source_verified(e.provenance)
        ]
        values = {str(e.raw).strip().lower() for e in approved}
        versions = {e.definition_id for e in approved}
        valid = len(versions) == 1 and len(values) == 1 and values <= {"true", "false"}
        state = "unknown"
        if valid:
            known += 1
            is_present = values == {"true"}
            present += is_present
            state = "present" if is_present else "verified_absent"
            definitions_used.extend(versions)
            entity_scopes.update(canonical(e.context["entity_scope"]) for e in approved)
        sources.extend(e.provenance for e in matches)
        gaps.append({"metric": code, "state": state})
    value = D(present) / D(len(DISCLOSURES)) * 100 if known else None
    reason = (
        "mixed_disclosure_entity_scopes"
        if len(entity_scopes) > 1
        else None if known == len(DISCLOSURES) else "incomplete_disclosure_assessment"
    )
    measure = Measure(
        "derived_disclosure_completeness",
        value,
        "%",
        {
            "checklist": list(DISCLOSURES),
            "assessed": known,
            "total": len(DISCLOSURES),
            "entity_scope": sorted(entity_scopes),
        },
        tuple(sorted(definitions_used)),
        sources,
        reason,
        "100 * validated_present_flags / 7; unassessed slots only lower this verified-coverage lower bound",
    )
    return measure, gaps


def components(
    metrics: dict[str, Measure], definitions: dict[str, Definition]
) -> dict[str, Any]:
    specs = [
        (
            "emissions_trajectory",
            "derived_yoy_emissions_change",
            D("0.45"),
            "clamp(50 - 2.5 * YoY percent, 0, 100)",
        ),
        (
            "renewable_energy",
            "derived_renewable_energy_adoption",
            D("0.35"),
            "renewable_energy_percent (not electricity share)",
        ),
        (
            "disclosure_completeness",
            "derived_disclosure_completeness",
            D("0.20"),
            "fully assessed seven-flag checklist percent",
        ),
    ]
    result: list[dict[str, Any]] = []
    for name, code, weight, formula in specs:
        measure = metrics[code]
        value = measure.value if measure.comparable else None
        reason = measure.reason
        if name == "renewable_energy" and value is not None:
            source_ids = [token.rsplit(":", 1)[-1] for token in measure.definitions]
            if any(
                definitions[i].score_eligibility != "conditional" for i in source_ids
            ):
                value, reason = None, "catalogue_not_score_eligible"
        if name == "emissions_trajectory" and value is not None:
            value = min(D(100), max(D(0), D(50) - D("2.5") * value))
        result.append(
            {
                "component": name,
                "metric": code,
                "weight": str(weight),
                "score": number(value),
                "reason": reason,
                "formula": formula,
                "provenance": measure.provenance,
            }
        )
    for name in ("governance", "net_zero_target"):
        result.append(
            {
                "component": name,
                "metric": None,
                "weight": "0",
                "score": None,
                "reason": "context_only_catalogue_not_score_eligible",
                "formula": "Excluded; policies and commitments are not achieved performance",
                "provenance": [],
            }
        )
    available = [c for c in result if c["score"] is not None]
    weight = sum((D(c["weight"]) for c in available), D(0))
    # Both performance components are mandatory: disclosure alone cannot create a score.
    performance_ready = all(result[i]["score"] is not None for i in (0, 1))
    trajectory = metrics["derived_yoy_emissions_change"]
    renewable = metrics["derived_renewable_energy_adoption"]
    aligned = all(
        trajectory.context.get(k) == renewable.context.get(k)
        for k in (
            "organisational_boundary",
            "period_start",
            "period_end",
            "consolidation_basis",
        )
    )
    score = (
        sum((D(c["score"]) * D(c["weight"]) for c in available), D(0)) / weight
        if performance_ready and aligned and weight >= D("0.8")
        else None
    )
    reason = (
        None
        if score is not None
        else (
            "component_boundaries_or_periods_differ"
            if performance_ready and not aligned
            else "requires_trajectory_and_renewable_energy"
        )
    )
    return {
        "label": LABEL,
        "value": number(score),
        "available_weight": str(weight),
        "coverage_percent": number(weight * 100),
        "reason": reason,
        "components": result,
        "ranking_eligible": False,
    }


def context_indicator(
    code: str, rows: list[EvidenceData], definitions: dict[str, Definition]
) -> dict[str, Any]:
    """Reviewed boolean evidence; absence of a row never implies false.

    Evidence references and assessment timestamps are audit metadata, not peer
    dimensions. All other required dimensions remain in the comparison key.
    """
    approved = [r for r in rows if r.state == "validated"]
    value: bool | None = None
    reason: str | None = "missing_validated_evidence"
    contexts: list[dict[str, Any]] = []
    tokens = sorted(
        {
            f"{code}:v{definitions[r.definition_id].version}:{r.definition_id}"
            for r in approved
        }
    )
    excluded = {
        "supporting_evidence",
        "reviewed_source_set",
        "scope3_observation_reference",
        "assessment_date",
    }
    if approved:
        reason = None
        for row in approved:
            context, missing = clean_context(row, definitions[row.definition_id])
            contexts.append({k: v for k, v in context.items() if k not in excluded})
            if not source_verified(row.provenance):
                reason = "source_or_validation_audit_missing"
            elif row.qualifier != "exact" or row.compatibility != "comparable":
                reason = "comparability_not_reviewed"
            elif missing:
                reason = "missing_comparison_dimensions"
        values = {str(r.raw).strip().lower() for r in approved}
        if (
            len(tokens) != 1
            or len({canonical(c) for c in contexts}) != 1
            or len(values) != 1
            or not values <= {"true", "false"}
        ):
            reason = "conflicting_or_invalid_context_evidence"
        if reason is None:
            value = values == {"true"}
    context = contexts[0] if contexts else {}
    return {
        "value": value,
        "reason": reason,
        "definition_ids": tokens,
        "comparison_dimensions": context,
        "cohort_key": (
            hashlib.sha256(canonical([tokens, context]).encode()).hexdigest()
            if reason is None
            else None
        ),
        "provenance": [r.provenance for r in rows],
    }


def statistics(
    subject: Measure, peers: list[tuple[str, Measure]], minimum: int
) -> dict[str, Any]:
    # Source-specific revenue attestations must not split otherwise identical emissions.
    subject_signature = signature(subject)
    # Caller passes a pre-indexed, comparable cohort with this exact signature.
    cohort = peers if subject.comparable else []
    values = [m.value for _, m in cohort if m.value is not None]
    ready = len(values) >= minimum
    midpoint = D(median(values)) if ready else None
    return {
        "peer_sample_size": len(values),
        "includes_subject": True,
        "minimum_sample_size": minimum,
        "percentile": (
            number(percentile(subject.value, values, minimum))
            if ready and subject.value is not None
            else None
        ),
        "median": number(midpoint),
        "distance_from_median": (
            number(subject.value - midpoint)
            if midpoint is not None and subject.value is not None
            else None
        ),
        "reason": subject.reason
        or (None if ready else "insufficient_comparable_peers"),
        "peer_company_ids": [cid for cid, _ in cohort],
        "cohort_key": (
            hashlib.sha256(subject_signature.encode()).hexdigest()
            if subject.comparable
            else None
        ),
        "flags": (
            ["highest_value"]
            if ready and len(set(values)) > 1 and subject.value == max(values)
            else []
        )
        + (
            ["lowest_value"]
            if ready and len(set(values)) > 1 and subject.value == min(values)
            else []
        ),
    }


def build(
    companies: list[CompanyData],
    definitions: list[Definition],
    evidence: list[EvidenceData],
    targets: list[dict[str, Any]],
    *,
    year: int,
    peer_group: PeerGroup = "sector",
    min_peers: int = 5,
    scope2_method: Scope2Method = "location_based",
) -> dict[str, Any]:
    if not 2000 <= year <= 2100 or not 5 <= min_peers <= 500:
        raise ValueError("Year must be 2000–2100; peer threshold must be 5–500")
    if peer_group not in {
        "sector",
        "country",
        "region",
        "industry",
        "revenue_band",
    } or scope2_method not in {"location_based", "market_based"}:
        raise ValueError("Unknown peer group or Scope 2 method")
    with localcontext() as context:
        context.prec = 64
        return _build(
            companies,
            definitions,
            evidence,
            targets,
            year,
            peer_group,
            min_peers,
            scope2_method,
        )


def _build(
    companies: list[CompanyData],
    definitions: list[Definition],
    evidence: list[EvidenceData],
    targets: list[dict[str, Any]],
    year: int,
    peer_group: PeerGroup,
    min_peers: int,
    scope2_method: Scope2Method,
) -> dict[str, Any]:
    defs = {d.id: d for d in definitions}
    evidence = sorted(
        [e for e in evidence if e.definition_id in defs and e.year in {year, year - 1}],
        key=lambda e: e.id,
    )
    # Only an explicitly validated successor for the same company/metric can retire evidence.
    by_id = {e.id: e for e in evidence}
    retired = {
        e.supersedes
        for e in evidence
        if e.state == "validated"
        and source_verified(e.provenance)
        and e.supersedes != e.id
        and e.supersedes in by_id
        and (e.company_id, e.definition_id, e.year)
        == (
            by_id[e.supersedes].company_id,
            by_id[e.supersedes].definition_id,
            by_id[e.supersedes].year,
        )
    }
    evidence = [e for e in evidence if e.id not in retired]
    grouped: dict[tuple[str, int, str], list[EvidenceData]] = defaultdict(list)
    for row in evidence:
        grouped[row.company_id, row.year, defs[row.definition_id].code].append(row)
    performance_codes = sorted({d.code for d in definitions if d.kind == "performance"})
    all_metrics: dict[str, dict[str, Measure]] = {}
    all_gaps: dict[str, list[dict[str, Any]]] = {}
    for company in companies:
        metrics = {
            code: resolve(code, grouped[company.id, year, code], defs)
            for code in performance_codes
        }

        def get(code: str) -> Measure:
            return metrics.get(code, Measure(code))

        total = combine(
            get("scope_1_emissions"), get(f"scope_2_{scope2_method}"), scope2_method
        )
        reconcile_total(total, get("scope_1_2_combined"))
        prior = combine(
            resolve(
                "scope_1_emissions",
                grouped[company.id, year - 1, "scope_1_emissions"],
                defs,
            ),
            resolve(
                f"scope_2_{scope2_method}",
                grouped[company.id, year - 1, f"scope_2_{scope2_method}"],
                defs,
            ),
            scope2_method,
        )
        reconcile_total(
            prior,
            resolve(
                "scope_1_2_combined",
                grouped[company.id, year - 1, "scope_1_2_combined"],
                defs,
            ),
        )
        metrics[total.code] = total
        metrics["derived_yoy_emissions_change"] = yoy(total, prior)
        metrics["derived_emissions_per_revenue"] = intensity(total, company, year)
        renewable = get("renewable_energy_percent")
        metrics["derived_renewable_energy_adoption"] = Measure(
            "derived_renewable_energy_adoption",
            renewable.value,
            renewable.unit,
            dict(renewable.context),
            renewable.definitions,
            list(renewable.provenance),
            renewable.reason,
            "renewable_energy_percent; no substitution of renewable electricity",
        )
        disclosure_metric, gaps = disclosure(
            [e for e in evidence if e.company_id == company.id and e.year == year], defs
        )
        metrics[disclosure_metric.code] = disclosure_metric
        all_gaps[company.id] = gaps
        # Attestation contains company-specific values and URLs, not comparison dimensions.
        for measure in metrics.values():
            measure.context.pop("revenue_alignment", None)
        all_metrics[company.id] = metrics
    ordered = sorted(companies, key=lambda c: (c.name.casefold(), c.id))
    peer_index: dict[tuple[str, str, str], list[tuple[str, Measure]]] = defaultdict(
        list
    )
    sector_index: dict[tuple[str, str, str], list[tuple[str, Measure]]] = defaultdict(
        list
    )
    counts: dict[str, int] = defaultdict(int)
    for company in ordered:
        group = peer_key(company, peer_group, year)
        if group is not None:
            counts[group] += 1
        for code, measure in all_metrics[company.id].items():
            if measure.comparable:
                key = signature(measure)
                if group is not None:
                    peer_index[group, code, key].append((company.id, measure))
                sector_index[company.sector.casefold(), code, key].append(
                    (company.id, measure)
                )
    items = []
    for company in ordered:
        group = peer_key(company, peer_group, year)
        metric_output = {}
        for code, measure in all_metrics[company.id].items():
            key = signature(measure)
            stats = statistics(
                measure, peer_index.get((group or "", code, key), []), min_peers
            )
            if group is None:
                stats["reason"] = measure.reason or "peer_group_unavailable"
            sector_stats = statistics(
                measure,
                sector_index.get((company.sector.casefold(), code, key), []),
                min_peers,
            )
            if code == "derived_yoy_emissions_change" and measure.value is not None:
                if "lowest_value" in stats["flags"] and measure.value < 0:
                    stats["flags"].append("biggest_yoy_decrease")
                if "highest_value" in stats["flags"] and measure.value > 0:
                    stats["flags"].append("biggest_yoy_increase")
            metric_output[code] = {
                "value": number(measure.value),
                "unit": measure.unit,
                "comparison_dimensions": measure.context,
                "definition_ids": list(measure.definitions),
                "eligibility_reason": measure.reason,
                "formula": measure.formula,
                "provenance": measure.provenance,
                **stats,
                "sector_median": sector_stats["median"],
                "sector_percentile": sector_stats["percentile"],
                "sector_sample_size": sector_stats["peer_sample_size"],
                "sector_distance_from_median": sector_stats["distance_from_median"],
            }
        company_targets = sorted(
            [
                t
                for t in targets
                if t["company_id"] == company.id and t["reporting_year"] == year
            ],
            key=lambda t: t["id"],
        )
        target_flags = [
            {
                "target_id": t["id"],
                "target_year": t["target_year"],
                "flag": (
                    "past_target_year"
                    if t["target_year"] < year
                    else "target_more_than_50_years_away"
                ),
            }
            for t in company_targets
            if t["validation_state"] == "validated"
            and source_verified(t)
            and (t["target_year"] < year or t["target_year"] > year + 50)
        ]
        items.append(
            {
                "company_id": company.id,
                "company_name": company.name,
                "sector": company.sector,
                "country": company.country,
                "region": company.region,
                "industry": company.industry,
                "revenue_band": revenue_band(company, year),
                "peer_group_value": group,
                "peer_group_company_count": counts.get(group or "", 0),
                "metrics": metric_output,
                "score": components(all_metrics[company.id], defs),
                "disclosure_gaps": [
                    g for g in all_gaps[company.id] if g["state"] != "present"
                ],
                "targets": company_targets,
                "target_flags": target_flags,
                "context_evidence": [
                    e.provenance
                    for e in evidence
                    if e.company_id == company.id
                    and e.year == year
                    and defs[e.definition_id].kind != "performance"
                ],
                "context_indicators": {
                    code: context_indicator(code, grouped[company.id, year, code], defs)
                    for code in (
                        "scope3_available",
                        "board_sustainability_oversight",
                        "scope3_supplier_engagement",
                    )
                },
            }
        )
    payload = {
        "methodology_version": VERSION,
        "label": LABEL,
        "year": year,
        "peer_group": peer_group,
        "minimum_peers": min_peers,
        "scope2_method": scope2_method,
        "percentile_definition": "Ascending midrank, subject included; numeric position, not sustainability merit",
        "persistence": "live_read_only",
        "total": len(items),
        "items": items,
    }
    payload["input_sha256"] = hashlib.sha256(
        canonical(
            {
                "companies": [vars(c) for c in ordered],
                "definitions": sorted(
                    [vars(d) for d in definitions], key=lambda d: d["id"]
                ),
                "evidence": [vars(e) for e in evidence],
                "targets": sorted(targets, key=lambda t: t["id"]),
                "parameters": [
                    VERSION,
                    "context-indicators-v1",
                    year,
                    peer_group,
                    min_peers,
                    scope2_method,
                ],
            }
        ).encode()
    ).hexdigest()
    return payload
