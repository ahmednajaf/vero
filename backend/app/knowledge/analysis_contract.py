"""Structured contracts for the master analytical brief; no model-specific types."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Fact(Closed):
    id: str
    metric: str
    value: str
    unit: str | None
    year: int | None
    population: str
    kind: Literal["actual", "target", "activity", "outcome", "contextual"]
    source_id: str
    excerpt: str = Field(min_length=5, max_length=1800)


class Promise(Closed):
    commitment: str
    deadline: str | None
    assessment: str
    fact_ids: list[str] = Field(min_length=1)


class Disclosure(Closed):
    criterion_id: Literal["scope1", "scope2", "scope3", "history", "renewables", "target", "credits", "workforce", "leadership", "training", "safety", "social", "assurance"]
    status: Literal["disclosed", "not_identified", "pending"]
    fact_ids: list[str]
    reason: str


class CompanyEvidence(Closed):
    facts: list[Fact]
    promises: list[Promise]
    disclosures: list[Disclosure]
    research_requests: list[str]


class Input(Closed):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,119}$")
    fact_id: str
    normalised_unit: str


class Step(Closed):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,119}$")
    operation: Literal["add", "subtract", "multiply", "divide", "power", "absolute"]
    operands: list[str] = Field(min_length=1, max_length=2)


class MetricRow(Closed):
    company_id: str
    inputs: list[Input] = Field(min_length=1, max_length=12)


class Metric(Closed):
    id: str
    name: str
    question: str
    definition: str
    formula: str
    steps: list[Step] = Field(min_length=1, max_length=20)
    result_step_id: str
    result_unit: str
    direction: Literal["higher", "lower", "near_reference", "none"]
    reference_value: str | None
    rows: list[MetricRow]
    interpretation: str
    scope_note: str


class Finding(Closed):
    id: str
    headline: str
    takeaway: str = Field(max_length=240)
    explanation: str
    business_implication: str
    fact_ids: list[str]
    metric_ids: list[str]
    counterpoint: str
    priority: Literal["lead", "supporting", "appendix"]


class RubricItem(Closed):
    id: str
    criterion: str
    evidence_required: str
    max_points: int = Field(ge=1, le=10)


class RubricAssessment(Closed):
    company_id: str
    criterion_id: str
    points: int = Field(ge=0, le=10)
    fact_ids: list[str]
    explanation: str


class Award(Closed):
    id: str
    name: str
    why_it_matters: str
    basis: Literal["numeric", "disclosure", "qualitative"]
    metric_id: str | None
    rubric: list[RubricItem]
    assessments: list[RubricAssessment]


class Outline(Closed):
    heading: str
    question: str
    finding_ids: list[str]
    metric_ids: list[str]
    award_ids: list[str]


class PeerAnalysis(Closed):
    analysis_title: str
    executive_questions: list[str]
    derived_metrics: list[Metric]
    findings: list[Finding]
    awards: list[Award]
    report_outline: list[Outline]
    research_requests: list[str]
    continuation_needed: bool = False


class MetricRepairs(Closed):
    derived_metrics: list[Metric]
    rejected_ids: list[str] = Field(default_factory=list)


class FindingCheck(Closed):
    finding_id: str
    outcome: Literal['unchanged', 'corrected', 'rejected']
    reason: str
    correction: Finding | None


class FindingReview(Closed):
    checks: list[FindingCheck]


class AwardCheck(Closed):
    award_id: str
    outcome: Literal['supported', 'clarified', 'rejected']
    name: str | None
    reason: str


class AwardReview(Closed):
    checks: list[AwardCheck]


# One frozen set per edition; the model assesses evidence, never changes weights.
CHECKLIST = {
    "scope1": ("Scope 1 emissions", '"scope 1"'),
    "scope2": ("Scope 2 with accounting method", '"scope 2" "market-based" "location-based"'),
    "scope3": ("Scope 3 with categories covered", '"scope 3"'),
    "history": ("Historical emissions on a stated basis", '"emissions" "baseline" "2024"'),
    "renewables": ("Renewable electricity or energy with denominator", '"renewable electricity" "renewable energy"'),
    "target": ("Quantified target and deadline", '"net zero" "target" "2030"'),
    "credits": ("Carbon-credit use and scope, including explicit zero", '"carbon credits" "offsets" "retired"'),
    "workforce": ("Workforce gender share", '"women" "female" "workforce"'),
    "leadership": ("Leadership gender share", '"women" "leadership" "management"'),
    "training": ("Training amount and population", '"training" "hours"'),
    "safety": ("Fatalities including contractor coverage", '"fatalities" "contractors"'),
    "social": ("Social investment amount", '"social investment" "community investment" "local development"'),
    "assurance": ("Independent assurance scope", '"independent assurance" "limited assurance"'),
}
