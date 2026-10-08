"""Conservative evidence gates; confidence never promotes evidence to validated."""

import re
from dataclasses import replace
from decimal import Decimal

from app.catalogue.contracts import Metric
from app.extraction.contracts import Assessed, Candidate, Retrieved
from app.extraction.normalisation import normalise
from app.extraction.retrieval import retrieve, words


def locate_excerpt(text: str, quote: str | None) -> tuple[int, int] | None:
    if not quote or not quote.strip():
        return None
    # Allow whitespace differences only and return the ORIGINAL substring.
    pattern = r"\s+".join(re.escape(part) for part in quote.split())
    match = re.search(pattern, text)
    return (match.start(), match.end()) if match else None


def literal_present(value: str, quote: str) -> bool:
    return (
        re.search(r"(?<![\w.,])" + re.escape(value.strip()) + r"(?![\w.,])", quote)
        is not None
    )


def source_years(value: str) -> set[str]:
    """Recognise explicit fiscal labels; do not equate fiscal and calendar periods."""
    years = set(re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", value))
    years.update(
        "20" + year for year in re.findall(r"\bFY\s*['’]?(\d{2})\b", value, re.I)
    )
    return years


def locate_table_lines(text: str, quote: str | None) -> tuple[int, int] | None:
    """Recover shortened tables from unique ordered whole lines, never fuzzy facts.

    Return the original contiguous span, including omitted columns and rows.
    """
    lines = [line.strip() for line in (quote or "").splitlines() if line.strip()]
    if len(lines) < 3 or not any(re.fullmatch(r"[\d,.]+", line) for line in lines):
        return None
    matches = []
    for line in lines:
        pattern = (
            r"(?m)^[ \t]*"
            + r"[ \t]+".join(re.escape(p) for p in line.split())
            + r"[ \t]*$"
        )
        found = list(re.finditer(pattern, text))
        if len(found) != 1:
            return None
        matches.append(found[0])
    if any(a.end() > b.start() for a, b in zip(matches, matches[1:])):
        return None
    if matches[-1].end() - matches[0].start() > 1800:
        return None
    return matches[0].start(), matches[-1].end()


def scope_row_matches(code: str, quote: str, raw: str) -> bool:
    """Nearby scope words elsewhere in a table are not proof of row identity."""
    expected = code.split("_")[1]
    occurrences = list(
        re.finditer(r"(?<![\w.,])" + re.escape(raw.strip()) + r"(?![\w.,])", quote)
    )
    if not occurrences:
        return False
    for occurrence in occurrences:
        prefix = quote[: occurrence.start()]
        labels = [
            line
            for line in prefix.splitlines()
            if re.search(
                r"\bemissions?(?:[ivx]{1,4})?\b|\bscope\s*[123]\b|\bcategory\s+\d",
                line,
                re.I,
            )
        ]
        if not labels:
            return False
        label = labels[-1]
        scopes = re.search(
            r"\bscope\s*([123])(?:\s*(?:,|and|&|/|\+)\s*(?:scope\s*)?([123]))?",
            label,
            re.I,
        )
        if scopes is None or scopes[1] != expected or scopes[2] is not None:
            return False
        if re.search(r"\b(intensity|target|reduction|avoided)\b", label, re.I):
            return False
    return True


def assess(
    metric: Metric, year: int, retrieved: Retrieved, candidate: Candidate
) -> Assessed:
    result = Assessed(candidate, retrieved, "needs_review", [])
    flags = result.flags
    if candidate.metric_id != metric.canonical_id:
        flags.append("metric_mismatch")
    if candidate.page_number != retrieved.passage.page:
        flags.append("page_mismatch")
    position = locate_excerpt(retrieved.passage.text, candidate.supporting_excerpt)
    if position is None:
        position = locate_table_lines(
            retrieved.passage.text, candidate.supporting_excerpt
        )
        if position:
            flags.append("shortened_table_quote_source_span_restored")
    if position is None:
        flags.append("excerpt_not_in_chunk")
    else:
        result.excerpt_start, result.excerpt_end = position
        result.excerpt = retrieved.passage.text[position[0] : position[1]]
        # A model may correctly quote a table's total row without its heading.
        # Attach only contiguous, bounded text from THE SAME supplied chunk.
        # Keep the original candidate untouched in the audit; this is context,
        # never a guessed row/column alignment or automatic approval.
        if metric.canonical_id.startswith("scope_") and not re.search(
            r"\bscope\s*[123]\b", result.excerpt, re.I
        ):
            before = retrieved.passage.text[max(0, position[0] - 1800) : position[0]]
            labels = list(re.finditer(r"(?m)^.*\bscope\s*[123]\b.*$", before, re.I))
            if labels:
                label_start = max(0, position[0] - 1800) + labels[-1].start()
                start = (
                    retrieved.passage.text.rfind("\n", 0, max(0, label_start - 160)) + 1
                )
                result.excerpt_start = start
                result.excerpt = retrieved.passage.text[start : position[1]]
                flags.append("table_header_context_attached_requires_review")
    quote = result.excerpt or ""
    raw = candidate.reported_value
    if raw is None or not raw.strip():
        flags.append("passage_absence_not_report_absence")
    elif not literal_present(raw, quote):
        flags.append("value_not_in_excerpt")
    if candidate.status == "not_reported" and raw is not None:
        flags.append("contradictory_model_status")
    if candidate.status != "extracted":
        flags.append("model_" + candidate.status)
    # Explicit observation year is distinct from report publication/request year.
    years = source_years(candidate.reporting_period or "")
    if str(year) not in years or str(year) not in source_years(retrieved.passage.text):
        flags.append("year_unsubstantiated")
    elif str(year) not in source_years(quote):
        flags.append("year_context_outside_excerpt")
    if re.search(
        r"\bFY\s*['’]?\d{2,4}\b|\bfiscal\b", candidate.reporting_period or "", re.I
    ):
        flags.append("fiscal_period_requires_alignment")
    if years - {str(year)}:
        flags.append("non_calendar_or_multi_year_period")
    if (
        candidate.reporting_period
        and locate_excerpt(retrieved.passage.text, candidate.reporting_period) is None
    ):
        flags.append("period_wording_not_in_chunk")
    if candidate.boundary is None:
        flags.append("boundary_unknown")
    elif locate_excerpt(retrieved.passage.text, candidate.boundary) is None:
        flags.append("boundary_not_in_chunk")
    if (
        candidate.reported_unit is not None
        and locate_excerpt(quote, candidate.reported_unit) is None
    ):
        flags.append("unit_not_in_excerpt")
    # A target observation is never written as achieved performance. Retain its
    # structured response in the extraction run for a later target-specific review.
    if metric.evidence_kind == "target":
        flags.append("target_requires_separate_review")
    if metric.evidence_kind == "performance":
        if re.search(
            r"\b(targets?|aims?|by 20\d\d|ambition|pledge|commitment|goal|forecast|projected|will reduce)\b",
            quote,
            re.I,
        ):
            flags.append("target_or_projection_context")
        if (
            re.search(r"\b(avoided|offsets?|removals?)\b", quote, re.I)
            and metric.category == "climate"
        ):
            flags.append("gross_vs_net_or_avoided_unclear")
    text = words(quote)
    parent_energy_label = (
        metric.canonical_id == "electricity_consumption"
        and "electricity" in text.split()
        and "energy consumption" in words(retrieved.passage.text)
    )
    if parent_energy_label:
        flags.append("metric_context_parent_section")
    if (
        quote
        and not parent_energy_label
        and not retrieve(
            [replace(retrieved.passage, text=quote)], metric, year, top_k=1
        )
    ):
        flags.append("metric_context_not_in_excerpt")
    if metric.canonical_id.startswith("scope_"):
        scope = metric.canonical_id.split("_")[1]
        if not re.search(rf"\bscope {scope}\b", text):
            flags.append("scope_not_explicit")
        if metric.canonical_id.startswith("scope_2_"):
            method = "location" if "location" in metric.canonical_id else "market"
            if method not in text.split():
                flags.append("scope2_method_not_explicit")
        if metric.canonical_id == "scope_1_2_combined" and not re.search(
            r"\bscope 1 (?:and |plus )?(?:scope )?2\b", text
        ):
            flags.append("combined_scope_not_explicit")
        if (
            raw
            and metric.canonical_id
            in {
                "scope_1_emissions",
                "scope_2_location_based",
                "scope_2_market_based",
                "scope_3_emissions",
            }
            and not scope_row_matches(metric.canonical_id, quote, raw)
        ):
            flags.append("scope_value_row_mismatch")
    if (
        metric.category == "climate"
        and metric.canonical_id != "emissions_intensity"
        and re.search(
            r"\bintensity\b|\bper\s+(?:unit|million|revenue)|/",
            candidate.reported_unit or "",
            re.I,
        )
    ):
        flags.append("intensity_not_absolute")
    if metric.canonical_id == "scope_3_emissions" and re.search(
        r"\bcategory\s+\d|purchased goods|business travel|financed emissions",
        quote,
        re.I,
    ):
        flags.append("scope3_partial_categories_possible")
    # Multi-year tables need column/row verification; presence of a year token
    # alone is never treated as proof that a nearby number belongs to that year.
    if len(source_years(retrieved.passage.text)) > 1:
        flags.append("multi_year_alignment_requires_review")
    normal = normalise(metric, raw, candidate.reported_unit)
    flags.extend(normal.flags)
    result.denominator = normal.denominator
    blockers = {
        "metric_mismatch",
        "page_mismatch",
        "excerpt_not_in_chunk",
        "value_not_in_excerpt",
        "passage_absence_not_report_absence",
        "year_unsubstantiated",
        "contradictory_model_status",
        "target_requires_separate_review",
        "target_or_projection_context",
        "scope_not_explicit",
        "scope2_method_not_explicit",
        "combined_scope_not_explicit",
        "intensity_not_absolute",
        "metric_context_not_in_excerpt",
        "scope_value_row_mismatch",
    }
    result.can_persist = not blockers.intersection(flags)
    unsafe_conversion = blockers | {
        "unit_not_in_excerpt",
        "gross_vs_net_or_avoided_unclear",
    }
    if not unsafe_conversion.intersection(flags):
        result.normalised_value, result.normalised_unit = normal.value, normal.unit
    if result.can_persist and "missing_intensity_denominator" in flags:
        result.state = "not_comparable"
    elif result.can_persist and not flags:
        result.state = "extracted"
    # No model self-confidence enters this transparent bounded heuristic.
    result.components = {
        "candidate_relevance": min(0.25, max(0, retrieved.score) / 40 * 0.25),
        "page_consistency": 0.15 if "page_mismatch" not in flags and position else 0,
        "year_match": 0.2 if "year_unsubstantiated" not in flags else 0,
        "unit_clarity": (
            0.15
            if normal.value is not None and "unit_not_in_excerpt" not in flags
            else 0
        ),
        "literal_value_support": (
            0.15 if raw is not None and "value_not_in_excerpt" not in flags else 0
        ),
        "repeated_corroboration": 0,
    }
    update_confidence(result)
    return result


def update_confidence(result: Assessed) -> None:
    score = sum(result.components.values())
    if result.flags:
        score = min(score, 0.6)
    if not result.can_persist:
        score = min(score, 0.25)
    result.confidence = Decimal(str(round(score, 4)))


def reconcile(results: list[Assessed]) -> None:
    values = [r for r in results if r.can_persist]
    for result in values:

        def identity(item: Assessed) -> tuple[Decimal | str | None, str | None]:
            return (
                (item.normalised_value, item.normalised_unit)
                if item.normalised_value is not None
                else (item.candidate.reported_value, item.candidate.reported_unit)
            )

        others = [r for r in values if r is not result]
        if any(identity(r) != identity(result) for r in others):
            result.flags.append("conflicting_candidates")
            result.state = "needs_review"
        elif any(
            r.retrieved.passage.page != result.retrieved.passage.page
            and r.candidate.boundary == result.candidate.boundary
            for r in others
        ):
            result.components["repeated_corroboration"] = 0.1
        update_confidence(result)
