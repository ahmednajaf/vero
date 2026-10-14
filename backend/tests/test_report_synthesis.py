"""Synthetic test fixtures only; never seeded as real-company findings."""
import asyncio
import csv
import io
from copy import deepcopy

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KnowledgeAnswer
from app.knowledge.briefings import export_csv, export_html
from app.knowledge.provider import Completion, ResearchError, request_body
from app.knowledge.synthesis import (
    AwardProposal, ReportSynthesis, assemble, award_result, research_packet,
    synthesise, unit_in_quote,
)
from app.knowledge.workspace import recent_answers
from test_openai_extraction import settings


COMPANIES = [{"id": "a", "company_name": "Fixture A"}, {"id": "b", "company_name": "Fixture B"}, {"id": "c", "company_name": "Fixture C"}]


def source(company, quote, identifier="page1"):
    return {"company_id": company, "company": f"Fixture {company.upper()}",
            "quote": quote, "text": quote, "evidence_id": f"{company}-{identifier}",
            "report": "Fixture annual report", "report_id": f"report-{company}",
            "page": 12, "source_url": "https://example.com/report.pdf",
            "report_sha256": "f" * 64}


def value(raw, unit, ref, year=2025):
    return {"raw_value": raw, "raw_unit": unit, "year": year, "source_id": ref}


def proposal(**overrides):
    return AwardProposal.model_validate({
        "name": "Lowest reported operational emissions",
        "criterion": "Lowest gross Scope 1 emissions among assessed companies in this cohort.",
        "operation": "value", "direction": "lower", "numerator_unit": "tCO2e",
        "denominator_unit": None, "contextual": False, "caveat": "Company size and business mix affect absolute emissions.",
        "entrants": [
            {"company_id": "a", "numerator": value("2", "MtCO2e", "S1")},
            {"company_id": "b", "numerator": value("1500", "ktCO2e", "S2")},
        ], **overrides,
    })


def sources():
    return {"S1": source("a", "2025 Scope 1 emissions: 2 MtCO2e; 2024: 2.5 MtCO2e."),
            "S2": source("b", "2025 Scope 1 emissions: 1500 ktCO2e; 2024: 2000 ktCO2e.")}


def packet():
    return {"sources": sources(), "companies": COMPANIES, "observation_year": 2025, "omitted_findings": 0}


def test_award_converts_units_without_manual_validation_and_preserves_original():
    result = award_result(proposal(), sources(), COMPANIES, 2025)
    assert result["winner_ids"] == ["b"]
    assert result["rows"][0]["value"] == "1500000"
    assert result["rows"][0]["inputs"][0]["raw_value"] == "1500"
    assert result["sample_size"] == 2 and result["cohort_size"] == 3
    assert result["unassessed_company_ids"] == ["c"]


def test_ties_have_joint_winners_and_do_not_depend_on_order():
    s = sources()
    s["S2"] = source("b", "2025 Scope 1 emissions: 2000 ktCO2e.")
    p = proposal(entrants=[proposal().entrants[0].model_dump(), {"company_id": "b", "numerator": value("2000", "ktCO2e", "S2")}])
    assert set(award_result(p, s, COMPANIES)["winner_ids"]) == {"a", "b"}
    p.entrants.reverse()
    assert set(award_result(p, s, COMPANIES)["winner_ids"]) == {"a", "b"}


def test_contextual_differences_remain_visible_without_false_award():
    result = award_result(proposal(contextual=True), sources(), COMPANIES)
    assert len(result["rows"]) == 2 and result["winner_ids"] == []
    assert result["status"] == "contextual_comparison"


@pytest.mark.parametrize("field,bad,reason", [
    ("raw_value", "3", "value_or_year_not_in_quote"),
    ("raw_unit", "kgCO2e", "raw_unit_not_in_quote"),
    ("source_id", "S2", "source_company_mismatch"),
    ("year", 2023, "value_or_year_not_in_quote"),
])
def test_unsupported_entry_does_not_destroy_other_comparison_rows(field, bad, reason):
    p = proposal()
    p.entrants[0].numerator = p.entrants[0].numerator.model_copy(update={field: bad})
    result = award_result(p, sources(), COMPANIES)
    assert result["excluded"][0]["reason"] == reason
    assert len(result["rows"]) == 1 and result["winner_ids"] == []


def test_different_years_are_contextual_not_ranked_together():
    p = proposal()
    p.entrants[0].numerator = p.entrants[0].numerator.model_copy(update={"raw_value": "2.5", "year": 2024})
    result = award_result(p, sources(), COMPANIES)
    assert len(result["rows"]) == 2 and result["winner_ids"] == []


def test_yoy_is_calculated_not_accepted_from_model():
    p = proposal(operation="percent_change", denominator_unit="tCO2e", entrants=[
        {"company_id": "a", "numerator": value("2", "MtCO2e", "S1"), "denominator": value("2.5", "MtCO2e", "S1", 2024)},
        {"company_id": "b", "numerator": value("1500", "ktCO2e", "S2"), "denominator": value("2000", "ktCO2e", "S2", 2024)},
    ])
    result = award_result(p, sources(), COMPANIES)
    assert result["winner_ids"] == ["b"]
    assert float(result["rows"][0]["value"]) == -25


def test_representation_bridge_ratio_and_percentage_point_gap():
    s = {"S1": source("a", "2025 women: workforce 40%; leadership 20%."),
         "S2": source("b", "2025 women: workforce 30%; leadership 30%.")}
    entrants = [{"company_id": "a", "numerator": value("20", "%", "S1"), "denominator": value("40", "%", "S1")},
                {"company_id": "b", "numerator": value("30", "%", "S2"), "denominator": value("30", "%", "S2")}]
    p = proposal(operation="ratio", direction="higher", numerator_unit="%", denominator_unit="%", entrants=entrants)
    result = award_result(p, s, COMPANIES)
    assert result["winner_ids"] == ["b"] and float(result["rows"][1]["value"]) == .5
    p.operation = "difference"
    result = award_result(p, s, COMPANIES)
    assert float(result["rows"][1]["value"]) == -20
    assert result["rows"][1]["unit"] == "percentage points"


def test_zero_denominator_is_not_zero_score():
    s = sources()
    s["S1"] = source("a", "2025 Scope 1: 2 MtCO2e; revenue 0 million USD.")
    s["S2"] = source("b", "2025 Scope 1: 1500 ktCO2e; revenue 2000 million USD.")
    p = proposal(operation="ratio", denominator_unit="million_USD", entrants=[
        {"company_id": "a", "numerator": value("2", "MtCO2e", "S1"), "denominator": value("0", "million USD", "S1")},
        {"company_id": "b", "numerator": value("1500", "ktCO2e", "S2"), "denominator": value("2000", "million USD", "S2")},
    ])
    result = award_result(p, s, COMPANIES)
    assert result["excluded"][0]["reason"] == "nonpositive_denominator"
    assert float(result["rows"][0]["value"]) == 750


def test_duplicate_company_rejected_not_arbitrarily_selected():
    p = proposal()
    p.entrants[1].company_id = "a"
    with pytest.raises(ValueError, match="duplicate_award_company"):
        award_result(p, sources(), COMPANIES)


@pytest.mark.parametrize("unit,quote", [("%", "women 35%"), ("MtCO2e", "million tonnes CO2e"), ("million_USD", "$ 300 million USD"), ("MWh", "megawatt-hours")])
def test_unit_aliases_in_source(unit, quote):
    assert unit_in_quote(unit, quote)


def test_unknown_sources_or_invented_numbers_do_not_poison_valid_insights():
    base = {"headline": "Reported scale differs", "observation": "The reported operational totals differ.",
            "implication": "Business mix should inform how the figures are interpreted.", "source_ids": ["S1", "S2"]}
    output = ReportSynthesis.model_validate({"insights": [base, {**base, "source_ids": ["MISSING"]}, {**base, "observation": "Emissions fell 90%."}], "awards": []})
    result = assemble(output, packet())
    assert len(result["claims"]) == 1 and result["status"] == "partial"
    assert result["insights"][0]["kind"] == "editorial_analysis"
    assert len(result["validation"]["warnings"]) == 2


def sections():
    return [{"id": "emissions", "title": "Emissions", "status": "completed", "result": {"claims": [
        {"text": "Fixture A reports Scope 1 emissions of 2 MtCO2e in 2025.", "citations": [sources()["S1"]]},
        {"text": "Fixture B reports Scope 1 emissions of 1500 ktCO2e in 2025.", "citations": [sources()["S2"]]},
    ]}}]


def test_packet_is_bounded_and_uses_only_existing_sources():
    data = research_packet({"companies": COMPANIES}, sections(), 10000)
    assert len(data["sources"]) == 2
    assert data["sources"]["S1"]["quote"] == sources()["S1"]["quote"]
    small = research_packet({"companies": COMPANIES}, sections(), 1)
    assert small["sources"] == {} and small["omitted_findings"] == 2


def test_schema_uses_strict_structured_output():
    body = request_body(settings(), {}, schema=ReportSynthesis)
    assert body["text"]["format"]["strict"]
    assert body["text"]["format"]["schema"]["additionalProperties"] is False


class SynthesisProvider:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    async def structured(self, payload, schema, instructions):
        self.calls += 1
        assert "AI spending" in instructions
        if self.fail:
            raise ResearchError("openai_timeout")
        data = ReportSynthesis(insights=[], awards=[proposal()])
        return Completion(data, 100, 80, 25, "fixture-mini")


def test_synthesis_reuses_ledger_cache_and_never_enters_chat_history(db_engine):
    provider = SynthesisProvider()
    definition = {"companies": COMPANIES, "observation_year": 2025}
    first = asyncio.run(synthesise(db_engine, definition, sections(), settings(), provider))
    second = asyncio.run(synthesise(db_engine, definition, sections(), settings(), provider))
    assert first["awards"][0]["winner_ids"] == ["b"]
    assert first["usage"]["input_tokens"] == 100
    assert second["cached"] and provider.calls == 1
    with Session(db_engine) as session:
        assert len(session.scalars(select(KnowledgeAnswer)).all()) == 1
        assert recent_answers(session)["items"] == []


def test_synthesis_failure_is_clear_without_retry(db_engine):
    provider = SynthesisProvider(fail=True)
    with pytest.raises(ResearchError, match="openai_timeout"):
        asyncio.run(synthesise(db_engine, {"companies": COMPANIES}, sections(), settings(), provider))
    assert provider.calls == 1


def test_empty_evidence_does_not_call_provider(db_engine):
    provider = SynthesisProvider()
    result = asyncio.run(synthesise(db_engine, {"companies": COMPANIES}, [], settings(), provider))
    assert not result["model_called"] and provider.calls == 0


def test_awards_export_criteria_values_and_input_sources():
    report = assemble(ReportSynthesis(insights=[], awards=[proposal()]), packet())
    payload = {"title": "Energy <script>", "created_at": "2026-10-13", "status": "ready", "sources_current": True,
               "definition": {"companies": COMPANIES}, "sections": [{"title": "Insights & awards", "status": "completed", "result": report}], "review_opportunities": []}
    html = export_html(payload)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "1500000" in html and "p. 12" in html and proposal().criterion in html
    rows = list(csv.reader(io.StringIO(export_csv(payload).lstrip("\ufeff"))))
    assert all(len(row) == len(rows[0]) for row in rows)
    assert "1500000" in rows[-1] or "1500000" in rows[-2]
