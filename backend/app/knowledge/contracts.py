from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Generated report sections belong in saved peer analyses, not chat history.
BRIEFING_PROMPT_PREFIX = "For a company briefing, analyse EACH of the selected companies; do not narrow the selected peer group. "


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_ids: list[UUID] = Field(default_factory=list, max_length=500)
    report_ids: list[UUID] = Field(default_factory=list, max_length=500)
    sector: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    report_year: int | None = Field(default=None, ge=2000, le=2100)


class SearchRequest(Scope):
    query: str = Field(min_length=2, max_length=600)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)


class AskRequest(Scope):
    question: str = Field(min_length=5, max_length=6000)
    parent_answer_id: UUID | None = None


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str = Field(min_length=1, max_length=50)
    quote: str = Field(min_length=10, max_length=1500)


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=5, max_length=1200)
    citations: list[Citation] = Field(min_length=1, max_length=6)


class ResearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal[
        "answered", "partial", "needs_clarification", "insufficient_evidence"
    ]
    claims: list[Claim]
    limitations: list[
        Literal[
            "sampled_evidence",
            "incompatible_comparison",
            "ranking_basis_missing",
            "target_not_achievement",
            "missing_evidence",
            "disclosure_census_unavailable",
        ]
    ] = Field(default_factory=list, max_length=4)
    follow_up_question: str | None = Field(default=None, max_length=300)


class ResearchPlan(BaseModel):
    """A bounded read-only research plan, not arbitrary SQL, URLs or tool code."""

    model_config = ConfigDict(extra="forbid")
    intent: Literal[
        "fact",
        "comparison",
        "discovery",
        "ranking",
        "disclosure_coverage",
        "library_coverage",
    ]
    queries: list[Annotated[str, Field(min_length=2, max_length=250)]] = Field(
        min_length=1, max_length=3
    )
    company_names: list[Annotated[str, Field(min_length=1, max_length=150)]] = Field(
        max_length=10
    )
    sector: str | None = Field(max_length=80)
    country: str | None = Field(pattern="^[A-Z]{2}$")
    # This is an observation year, never silently a document/publication-year filter.
    observation_year: int | None = Field(ge=2000, le=2100)
    metric_code: str | None = Field(max_length=100)
    comparison_basis: str | None = Field(max_length=300)

    @classmethod
    def from_question(cls, question: str) -> "ResearchPlan":
        """Non-AI preview only; the live answer uses the model's validated plan."""
        return cls(
            intent="fact",
            queries=[question[:250]],
            company_names=[],
            sector=None,
            country=None,
            observation_year=None,
            metric_code=None,
            comparison_basis=None,
        )
