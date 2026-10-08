"""Exact Decimal arithmetic with explicit units. No LLM arithmetic or guessing."""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext

from app.catalogue.contracts import Metric


@dataclass(frozen=True)
class Normalised:
    value: Decimal | None
    unit: str | None
    flags: tuple[str, ...] = ()
    denominator: str | None = None


def number(raw: str) -> Decimal | None:
    # Explicit English grouping only; decimal commas, ranges and magnitude words
    # are not guessed. Original raw text is retained regardless of acceptance.
    value = unicodedata.normalize("NFKC", raw).strip().replace("−", "-")
    if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", value):
        return None
    try:
        result = Decimal(value.replace(",", ""))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def unit_key(raw: str) -> str:
    value = unicodedata.normalize("NFKC", raw).strip()
    aliases = {
        "percent": "%",
        "percentage": "%",
        "per cent": "%",
        "cubic metres": "m3",
        "cubic meters": "m3",
        "litres": "L",
        "liters": "L",
        "megalitres": "ML",
        "metric tonnes": "t",
        "metric tons": "t",
        "tonnes": "t",
        "kilograms": "kg",
        "thousand tonnes": "kt",
        "individuals": "persons",
        "people": "persons",
        "employees": "persons",
    }
    if value.casefold() in aliases:
        return aliases[value.casefold()]
    # SI magnitude is deliberately case-sensitive: Mt is not mt.
    compact = (
        re.sub(r"\s+", "", value).replace("CO2-eq", "CO2e").replace("CO2eq", "CO2e")
    )
    if compact in {"kgCO2e", "tCO2e", "ktCO2e", "MtCO2e"}:
        return compact
    match = re.fullmatch(
        r"(million |thousand |1,000 )?(metric tons|metric tonnes|tonnes|kilograms) (?:of )?co2(?:e| equivalent)",
        value.casefold(),
    )
    if match:
        scale, mass = match.groups()
        if mass == "kilograms":
            return "kgCO2e" if scale is None else value
        return {
            None: "tCO2e",
            "million ": "MtCO2e",
            "thousand ": "ktCO2e",
            "1,000 ": "ktCO2e",
        }[scale]
    return compact


def normalise(metric: Metric, raw: str | None, unit: str | None) -> Normalised:
    if raw is None:
        return Normalised(None, None, ("missing_value",))
    if metric.data_type not in {"decimal", "integer"}:
        # Qualitative/compound values require semantic review; never invent
        # numeric encodings that imply an ordinal ESG score.
        return Normalised(None, None, ("qualitative_value_requires_review",))
    value = number(raw)
    if value is None:
        return Normalised(None, None, ("ambiguous_numeric_format",))
    if unit is None or not unit.strip():
        flag = (
            "missing_intensity_denominator"
            if metric.canonical_id == "emissions_intensity"
            else "missing_unit"
        )
        return Normalised(None, None, (flag,))
    denominator = None
    canonical_unit = metric.canonical_unit
    key = unit_key(unit)
    if metric.canonical_id == "emissions_intensity":
        parts = re.split(r"\s+per\s+|/", unit, maxsplit=1)
        if (
            len(parts) != 2
            or not parts[1].strip()
            or parts[1].strip().lower()
            in {"unit", "output", "?", "unknown", "denominator_unit"}
        ):
            return Normalised(None, None, ("missing_intensity_denominator",))
        denominator = parts[1].strip()
        key = unit_key(parts[0])
        factors = {"kgCO2e": "0.001", "tCO2e": "1", "ktCO2e": "1000"}
        canonical_unit = f"tCO2e/{denominator}"
    elif metric.canonical_id == "yoy_emissions_change":
        factors = {"%": "1", "fraction": "100"}
    else:
        factors = metric.normalisation_rule.factors_to_canonical
    if key not in factors or canonical_unit is None or len(canonical_unit) > 80:
        return Normalised(None, None, ("unknown_or_incompatible_unit",), denominator)
    with localcontext() as context:
        context.prec = 80
        result = value * Decimal(factors[key])
    constraints = metric.validation_constraints
    if (
        (constraints.minimum is not None and result < Decimal(constraints.minimum))
        or (constraints.maximum is not None and result > Decimal(constraints.maximum))
        or (constraints.integer_only and result != result.to_integral_value())
    ):
        return Normalised(None, None, ("value_out_of_range",), denominator)
    # PostgreSQL numeric(38,12): refuse silent rounding or overflow.
    with localcontext() as context:
        context.prec = 80
        if abs(result) >= Decimal("1e26") or result != result.quantize(
            Decimal("1e-12")
        ):
            return Normalised(None, None, ("numeric_storage_precision",), denominator)
    return Normalised(result, canonical_unit, (), denominator)
