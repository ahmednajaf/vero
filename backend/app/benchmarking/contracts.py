from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

PeerGroup = Literal["sector", "country", "region", "industry", "revenue_band"]
Scope2Method = Literal["location_based", "market_based"]
VERSION = "benchmark-v1"
LABEL = "Prototype benchmark score — not an external ESG rating."
DISCLOSURES = (
    "scope1_available",
    "scope2_available",
    "scope3_available",
    "methodology_stated",
    "boundaries_stated",
    "assurance_available",
    "base_year_stated",
)


@dataclass(frozen=True)
class CompanyData:
    id: str
    name: str
    sector: str
    country: str
    region: str
    industry: str
    revenue: Decimal | None = None
    revenue_year: int | None = None
    currency: str | None = None


@dataclass(frozen=True)
class Definition:
    id: str
    code: str
    version: int
    unit: str | None
    kind: str
    required: tuple[str, ...]
    score_eligibility: str | None = None
    warning: str | None = None


@dataclass(frozen=True)
class EvidenceData:
    id: str
    company_id: str
    definition_id: str
    year: int
    state: str
    value: Decimal | None
    unit: str | None
    raw: str | None
    qualifier: str
    compatibility: str
    context: dict[str, Any]
    provenance: dict[str, Any]
    supersedes: str | None = None


@dataclass
class Measure:
    code: str
    value: Decimal | None = None
    unit: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    definitions: tuple[str, ...] = ()
    provenance: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = "missing_validated_evidence"
    formula: str | None = None

    @property
    def comparable(self) -> bool:
        return self.value is not None and self.reason is None
