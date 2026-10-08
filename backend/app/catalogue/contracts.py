from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal[
    "climate",
    "energy",
    "targets",
    "water",
    "waste",
    "governance",
    "social",
    "supply_chain",
    "disclosure_quality",
]
DataType = Literal["decimal", "integer", "boolean", "enum", "text", "object"]
Eligibility = Literal["not_eligible", "conditional"]
EvidenceKind = Literal["performance", "target", "governance", "disclosure", "programme"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class NormalisationRule(Contract):
    id: str
    version: str
    kind: Literal["scale", "identity", "contextual", "enum_map", "structured"]
    description: str = Field(min_length=20)
    # Exact decimal strings, not binary floating point or executable expressions.
    factors_to_canonical: dict[str, str] = {}
    value_aliases: dict[str, str] = {}
    canonical_unit_template: str | None = None
    requires_context: list[str] = []
    unknown_unit_action: Literal["needs_review"] = "needs_review"
    preserves_raw: Literal[True] = True

    @model_validator(mode="after")
    def exact_factors(self) -> Self:
        for value in self.factors_to_canonical.values():
            factor = Decimal(value)
            if not factor.is_finite() or factor <= 0:
                raise ValueError("Unit factors must be finite positive decimal strings")
        return self


class ValidationConstraints(Contract):
    nullable: Literal[True] = True
    missing_is_zero: Literal[False] = False
    absence_is_false: Literal[False] = False
    finite: bool = False
    minimum: str | None = None
    maximum: str | None = None
    integer_only: bool = False
    enum_values: list[str] = []
    value_schema: dict[str, object] | None = None
    required_context: list[str]
    rules: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_bounds(self) -> Self:
        bounds = [Decimal(v) for v in (self.minimum, self.maximum) if v is not None]
        if any(not value.is_finite() for value in bounds):
            raise ValueError("Bounds must be finite decimals")
        if len(bounds) == 2 and bounds[0] > bounds[1]:
            raise ValueError("Reversed validation bounds")
        return self


class Metric(Contract):
    canonical_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$", max_length=100)
    definition_version: int = Field(ge=1)
    catalogue_version: str
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=20)
    category: Category
    evidence_kind: EvidenceKind
    data_type: DataType
    quantity_kind: str
    canonical_unit: str | None
    allowed_units: list[str]
    aliases: list[str] = Field(min_length=1)
    normalisation_rule: NormalisationRule
    comparability_warning: str = Field(min_length=20)
    score_eligibility: Eligibility
    preferred_direction: Literal["lower", "higher"] | None
    validation_constraints: ValidationConstraints
    required_comparison_dimensions: list[str] = Field(min_length=1)
    sector_applicability: list[str] = Field(min_length=1)
    scope: str

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        if len({a.casefold() for a in self.aliases}) != len(self.aliases):
            raise ValueError("Duplicate metric aliases")
        if len(set(self.allowed_units)) != len(self.allowed_units):
            raise ValueError("Duplicate units")
        if (
            self.canonical_unit is not None
            and self.canonical_unit not in self.allowed_units
        ):
            raise ValueError("Canonical unit must be allowed")
        if self.normalisation_rule.kind == "scale":
            factors = self.normalisation_rule.factors_to_canonical
            if (
                set(factors) != set(self.allowed_units)
                or self.canonical_unit is None
                or Decimal(factors[self.canonical_unit]) != 1
            ):
                raise ValueError(
                    "Scale rules require complete factors and canonical identity"
                )
        if self.data_type == "enum":
            values = self.validation_constraints.enum_values
            if not values or any(
                v not in values for v in self.normalisation_rule.value_aliases.values()
            ):
                raise ValueError("Enum mappings require known values")
        if self.score_eligibility == "conditional" and (
            self.evidence_kind != "performance"
            or self.data_type not in {"integer", "decimal"}
            or self.preferred_direction is None
        ):
            raise ValueError(
                "Only numeric performance measures may be conditionally scored"
            )
        if self.evidence_kind != "performance" and self.preferred_direction is not None:
            raise ValueError(
                "No preferred performance direction for targets/disclosures"
            )
        if self.data_type == "object" and not self.validation_constraints.value_schema:
            raise ValueError("Structured metrics require a value schema")
        return self


class Catalogue(Contract):
    catalogue_version: str
    definition_policy: str
    reference_sources: list[dict[str, str]]
    metrics: list[Metric]

    @model_validator(mode="after")
    def unique_codes(self) -> Self:
        codes = [m.canonical_id for m in self.metrics]
        if len(set(codes)) != len(codes):
            raise ValueError("Canonical IDs must be unique")
        if any(m.catalogue_version != self.catalogue_version for m in self.metrics):
            raise ValueError("Mixed catalogue versions")
        return self


class MetricResponse(Metric):
    id: UUID
    is_active: bool


class MetricCatalogueResponse(Contract):
    catalogue_version: str
    total: int
    category_counts: dict[str, int]
    score_eligibility_counts: dict[str, int]
    items: list[MetricResponse]
    ranking_notice: str = "Conditional eligibility is not approval to rank. The prototype benchmarking engine requires validated, like-for-like evidence and reports insufficient context explicitly. Targets and governance remain contextual, not achieved performance."
