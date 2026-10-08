from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PIPELINE_VERSION = "metric-extraction-v2"
SCHEMA_VERSION = "metric-candidate-v1"
PROMPT_VERSION = "1.1.0"
RETRIEVAL_VERSION = "lexical-v4"
QUALITY_VERSION = "metric-quality-v7-table-source-span"
NORMALISATION_VERSION = "decimal-units-v2"


class Candidate(BaseModel):
    """Verbatim strings preserve precision, separators, units and source wording."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    metric_id: str = Field(min_length=1, max_length=100)
    reported_value: str | None = Field(max_length=1000)
    reported_unit: str | None = Field(max_length=200)
    reporting_period: str | None = Field(max_length=160)
    boundary: str | None = Field(max_length=500)
    page_number: int | None = Field(ge=1)
    supporting_excerpt: str | None = Field(max_length=4200)
    confidence: float | None = Field(ge=0, le=1)
    notes: str | None = Field(max_length=1200)
    status: Literal["extracted", "not_reported", "ambiguous", "needs_review"]


class CandidateBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    candidates: list[Candidate] = Field(min_length=1, max_length=6)


@dataclass(frozen=True)
class Passage:
    chunk_id: UUID
    report_id: UUID
    parse_run_id: UUID
    page: int
    text: str = field(repr=False)
    sha256: str
    section: str | None = None
    printed_page: str | None = None
    page_offset: int = 0


@dataclass(frozen=True)
class Retrieved:
    passage: Passage
    score: float
    matched_terms: tuple[str, ...]


@dataclass
class Assessed:
    candidate: Candidate
    retrieved: Retrieved
    state: str
    flags: list[str]
    normalised_value: Decimal | None = None
    normalised_unit: str | None = None
    denominator: str | None = None
    excerpt: str | None = None
    excerpt_start: int | None = None
    excerpt_end: int | None = None
    confidence: Decimal = Decimal("0")
    components: dict[str, float] = field(default_factory=dict)
    # A failed citation stays in the run audit, never becomes fabricated evidence.
    can_persist: bool = False
