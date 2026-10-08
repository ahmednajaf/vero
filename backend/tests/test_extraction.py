import asyncio
import argparse
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalogue.seed import load_catalogue
from app.core.config import Settings
from app.db.models import (
    Company,
    DocumentChunk,
    DocumentPage,
    ExtractionRun,
    MetricObservation,
    Report,
    ValidationEvent,
)
from app.extraction.contracts import Candidate, CandidateBatch, Passage, Retrieved
from app.extraction.normalisation import normalise, number
from app.extraction.prompts import extraction_prompt
from app.extraction.quality import (
    assess,
    reconcile,
    scope_row_matches,
    locate_table_lines,
)
from app.extraction.retrieval import retrieve
from app.extraction.service import extract_metric, observation_provenance, sha
from app.extraction.cli import execute, run_command
from app.extraction.recheck import recheck_scope_rows
from app.llm.contracts import ExtractionError, ModelIdentity, StructuredResult
from app.llm.prompts import INSTRUCTION_VERSION
from app.llm.schema import output_schema
from app.services.company_import import import_companies

FIXTURES = json.loads((Path(__file__).parent / "fixtures/extraction.json").read_text())
METRICS = {m.canonical_id: m for m in load_catalogue().metrics}
IDENTITY = ModelIdentity("ollama", "fixture-local:small", "a" * 64)


def test_shortened_quote_recovers_only_unique_ordered_whole_table_lines():
    source = "GHG Emissions (kg CO2e)\nFY25\nFY24\nScope 1\n13,000\n12,500"
    quote = "GHG Emissions (kg CO2e)\nScope 1\n12,500"
    result = checked(
        source,
        candidate(
            source, supporting_excerpt=quote, reporting_period="FY24", boundary=None
        ),
    )
    assert result.can_persist and result.excerpt == source
    assert result.candidate.supporting_excerpt == quote
    assert "shortened_table_quote_source_span_restored" in result.flags
    assert locate_table_lines(source, quote.replace("12,500", "12,501")) is None
    assert locate_table_lines(source + "\n12,500", quote) is None
    assert (
        locate_table_lines(source, "Scope 1\nGHG Emissions (kg CO2e)\n12,500") is None
    )


def test_scope_three_category_cannot_be_mislabelled_as_total():
    quote = "Scope 3\n1500\nCategory 1\n1400"
    assert scope_row_matches("scope_3_emissions", quote, "1500")
    assert not scope_row_matches("scope_3_emissions", quote, "1400")


def test_plain_scope_labels_do_not_require_repeated_emissions_heading():
    quote = "Emissions (tCO2e)\n2024\nScope 1\n12500\nScope 2 location-based\n9900"
    assert scope_row_matches("scope_1_emissions", quote, "12500")
    assert not scope_row_matches("scope_1_emissions", quote, "9900")
    assert scope_row_matches("scope_2_location_based", quote, "9900")
    assert not scope_row_matches("scope_2_location_based", quote, "12500")


def test_fiscal_year_shorthand_is_retained_not_silently_calendar_aligned():
    source = "Global operations\nGHG emissions (kg CO2e)\nFY25\nFY24\nScope 1\n13,000\n12,500"
    c = candidate(source, reporting_period="FY24")
    result = checked(source, c)
    assert result.can_persist
    assert "fiscal_period_requires_alignment" in result.flags
    assert "multi_year_alignment_requires_review" in result.flags
    assert "year_unsubstantiated" not in result.flags
    assert result.state == "needs_review"


def test_total_row_gets_verbatim_table_context_not_a_synthetic_quote():
    source = "2024 Global operations\nScope 1 emissions (kg CO2e)\nSites\n12,500\nTotal\n12,500"
    c = candidate(source, supporting_excerpt="Total\n12,500")
    result = checked(source, c)
    assert result.can_persist and result.state == "needs_review"
    assert result.excerpt in source
    assert result.candidate.supporting_excerpt == "Total\n12,500"
    assert "table_header_context_attached_requires_review" in result.flags
    wrong = checked(
        source.replace("Scope 1", "Scope 2"),
        candidate(source, supporting_excerpt="Total\n12,500"),
    )
    assert not wrong.can_persist


def passage(value, page=1):
    return Passage(uuid4(), uuid4(), uuid4(), page, value, sha(value))


def candidate(
    source, value="12,500", unit="kg CO2e", metric="scope_1_emissions", **changes
):
    return Candidate(
        **(
            {
                "metric_id": metric,
                "reported_value": value,
                "reported_unit": unit,
                "reporting_period": "2024",
                "boundary": "Global operations",
                "page_number": 1,
                "supporting_excerpt": source,
                "confidence": 0.99,
                "notes": None,
                "status": "extracted",
            }
            | changes
        )
    )


def checked(source, c=None, code="scope_1_emissions", page=1):
    return assess(
        METRICS[code],
        2024,
        Retrieved(passage(source, page), 32, ()),
        c or candidate(source, metric=code),
    )


def test_clean_table_exact_decimal_provenance_no_automatic_validation():
    source = FIXTURES["clean_emissions_table"]
    result = checked(source)
    assert result.can_persist and result.state == "extracted"
    assert (
        result.normalised_value == Decimal("12.5") and result.normalised_unit == "tCO2e"
    )
    assert result.candidate.reported_unit == "kg CO2e"
    assert source[result.excerpt_start : result.excerpt_end] == result.excerpt
    assert result.confidence < Decimal("0.99")


@pytest.mark.parametrize(
    "unit,value,expected",
    [
        ("kg CO2e", "125,000", "125"),
        ("kt CO2e", "0.125", "125"),
        ("Mt CO2e", "0.000125", "125"),
        ("1,000 tonnes CO₂e", "4,725", "4725000"),
        ("metric tons CO2e", "7", "7"),
        ("Metric tons CO2e", "65,763", "65763"),
        ("Million metric tonnes CO2e", "2", "2000000"),
    ],
)
def test_ghg_units(unit, value, expected):
    result = normalise(METRICS["scope_1_emissions"], value, unit)
    assert result.value == Decimal(expected) and not result.flags


@pytest.mark.parametrize("unit", ["kg CO2", "tons", "mtCO2e", "unknown", "tCO2e/USD"])
def test_unknown_or_wrong_quantity_never_guessed(unit):
    assert normalise(METRICS["scope_1_emissions"], "12", unit).value is None


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        ("50", "%", "50"),
        ("0.5", "%", "0.5"),
        ("0.5", "fraction", "50"),
        ("101", "%", None),
        ("1.1", "fraction", None),
        ("-1", "%", None),
        (None, "%", None),
    ],
)
def test_percent_bounds_explicit_fraction_and_null(value, unit, expected):
    result = normalise(METRICS["renewable_electricity_percent"], value, unit)
    assert result.value == (Decimal(expected) if expected is not None else None)


@pytest.mark.parametrize(
    "value", ["NaN", "1,25", "< 5", "1–2", "1 million", "1e100", ""]
)
def test_unclear_numeric_format_retained_for_review(value):
    assert number(value) is None


def test_missing_scope3_is_not_zero_or_report_level_absence():
    source = FIXTURES["missing_scope_3"]
    c = candidate(
        source, value=None, unit=None, metric="scope_3_emissions", status="not_reported"
    )
    result = checked(source, c, "scope_3_emissions")
    assert not result.can_persist and result.normalised_value is None
    assert "passage_absence_not_report_absence" in result.flags
    # A model cannot infer Scope 3 from explicitly supplied Scope 1.
    c = candidate(
        "2024 Global operations Scope 1 emissions: 12 tCO2e.",
        value="12",
        unit="tCO2e",
        metric="scope_3_emissions",
    )
    assert (
        "scope_not_explicit"
        in checked(c.supporting_excerpt, c, "scope_3_emissions").flags
    )


def test_target_vs_achieved_and_target_catalogue_never_performance():
    source = FIXTURES["targets_vs_actuals"]
    assert checked(source, candidate(source, "50", "tCO2e")).can_persist is False
    excerpt = "2024\nGlobal operations\nScope 1 emissions: 120 tCO2e."
    actual = checked(source, candidate(excerpt, "120", "tCO2e"))
    assert actual.can_persist and "target_or_projection_context" not in actual.flags
    target = "2024 Global operations Net zero target year is 2050."
    result = checked(
        target,
        candidate(target, "2050", "year", "net_zero_target_year"),
        "net_zero_target_year",
    )
    assert not result.can_persist and "target_requires_separate_review" in result.flags


def test_multi_year_alignment_not_auto_approved_wrong_year_rejected():
    source = FIXTURES["multi_year_table"]
    result = checked(source, candidate(source, "120", "tCO2e"))
    assert result.can_persist and result.state == "needs_review"
    assert "multi_year_alignment_requires_review" in result.flags
    wrong = candidate(source, "130", "tCO2e", reporting_period="2023")
    assert not checked(source, wrong).can_persist


def test_missing_intensity_denominator_is_not_comparable():
    source = FIXTURES["intensity_only"]
    result = checked(
        source,
        candidate(source, "2.5", "kg CO2e per unit", "emissions_intensity"),
        "emissions_intensity",
    )
    assert result.can_persist and result.state == "not_comparable"
    assert result.normalised_value is None
    complete = normalise(METRICS["emissions_intensity"], "2.5", "kg CO2e per MWh")
    assert complete.value == Decimal("0.0025") and complete.unit == "tCO2e/MWh"


def test_conflicts_retain_both_and_equivalent_units_corroborate():
    first, second = FIXTURES["conflicting_values"]
    values = [
        checked(first, candidate(first, "120", "tCO2e")),
        checked(second, candidate(second, "125", "tCO2e", page_number=2), page=2),
    ]
    reconcile(values)
    assert all(
        v.state == "needs_review" and "conflicting_candidates" in v.flags
        for v in values
    )
    sources = FIXTURES["different_units"]
    values = [
        checked(s, candidate(s, v, u, page_number=i), page=i)
        for i, (s, v, u) in enumerate(
            zip(
                sources,
                ["125,000", "0.125", "0.000125"],
                ["kg CO2e", "kt CO2e", "Mt CO2e"],
            ),
            1,
        )
    ]
    reconcile(values)
    assert all(v.normalised_value == 125 and v.state == "extracted" for v in values)
    assert all(v.components["repeated_corroboration"] == 0.1 for v in values)


@pytest.mark.parametrize(
    "change,flag",
    [
        ({"page_number": 2}, "page_mismatch"),
        ({"reported_value": "999"}, "value_not_in_excerpt"),
        ({"supporting_excerpt": "fabricated"}, "excerpt_not_in_chunk"),
        ({"metric_id": "scope_3_emissions"}, "metric_mismatch"),
        ({"boundary": "Invented subsidiary"}, "boundary_not_in_chunk"),
    ],
)
def test_citation_errors_flagged(change, flag):
    source = FIXTURES["clean_emissions_table"]
    result = checked(source, candidate(source, **change))
    assert flag in result.flags and result.state == "needs_review"
    if flag != "boundary_not_in_chunk":
        assert not result.can_persist


def test_retrieval_stable_page_bounded_tables_above_index_no_scope3_inference():
    table = passage(FIXTURES["clean_emissions_table"])
    unrelated = passage("Biodiversity and restoration programme. " * 20, 2)
    index = passage("SASB Index\nScope 1 emissions 2024 see page 20", 3)
    assert (
        retrieve([unrelated, index, table], METRICS["scope_1_emissions"], 2024)[
            0
        ].passage
        == table
    )
    assert not retrieve([table], METRICS["scope_3_emissions"], 2024)
    assert not retrieve([passage(table.text * 100)], METRICS["scope_1_emissions"], 2024)
    retrieved = Retrieved(table, 20, ())
    prompt = extraction_prompt(METRICS["scope_1_emissions"], 2024, retrieved)
    assert unrelated.text not in prompt.text and len(prompt.text) < 8000
    assert (
        json.loads(prompt.text.split("SOURCE DATA (JSON):\n")[1])["source_passage"]
        == table.text
    )


def test_strict_output_schema_and_nulls():
    source = FIXTURES["clean_emissions_table"]
    c = candidate(source)
    with pytest.raises(ValidationError):
        Candidate.model_validate(c.model_dump() | {"invented": True})
    with pytest.raises(ValidationError):
        Candidate.model_validate(c.model_dump() | {"reported_value": 12500})
    with pytest.raises(ValidationError):
        CandidateBatch(candidates=[])


class FakeExtractor:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []

    async def model_identity(self):
        return IDENTITY

    async def extract_structured(self, prompt, schema):
        self.calls.append(prompt)
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        data = schema.model_validate({"candidates": [c.model_dump() for c in output]})
        return StructuredResult(
            data,
            data.model_dump_json(),
            IDENTITY.name,
            IDENTITY.digest,
            prompt.name,
            prompt.version,
            sha(prompt.text),
            sha(
                json.dumps(
                    output_schema(schema),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            ),
            INSTRUCTION_VERSION,
            2.0,
            1.0,
            1,
        )


@pytest.fixture
def saved_report(db_engine, company_row, csv_file):
    import_companies(csv_file([company_row]), db_engine)

    def save(texts, *, statuses=None):
        with Session(db_engine) as session:
            report = Report(
                company_id=session.scalar(select(Company.id)),
                title="Fictional extraction fixture",
                report_type="sustainability",
                source_url="https://example.com/report.pdf",
                content_sha256="c" * 64,
                status="downloaded",
                page_count=len(texts),
            )
            session.add(report)
            session.flush()
            run = ExtractionRun(
                report_id=report.id,
                stage="parsing",
                status="succeeded",
                idempotency_key=uuid4().hex,
                input_sha256=report.content_sha256,
                code_version="fixture",
                schema_version="fixture",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
            session.add(run)
            session.flush()
            for index, source in enumerate(texts):
                page = DocumentPage(
                    report_id=report.id,
                    parse_run_id=run.id,
                    page_number=index + 1,
                    width_points=600,
                    height_points=800,
                    rotation=0,
                    raw_text=source,
                    raw_text_sha256=sha(source),
                    ordered_text=source,
                    ordered_text_sha256=sha(source),
                    text_characters=len(source),
                    status=statuses[index] if statuses else "parsed",
                    headings=[],
                    layout={},
                    warnings=[],
                    parser_name="fixture",
                    parser_version="1",
                )
                session.add(page)
                session.flush()
                session.add(
                    DocumentChunk(
                        report_id=report.id,
                        parse_run_id=run.id,
                        document_page_id=page.id,
                        chunk_index=index,
                        physical_page_start=index + 1,
                        physical_page_end=index + 1,
                        text=source,
                        text_sha256=sha(source),
                        chunk_type="text",
                        parser_name="fixture",
                        parser_version="1",
                        source_char_start=0,
                        source_char_end=len(source),
                        source_spans=[],
                    )
                )
            session.commit()
            return report.id

    return save


def run(db_engine, report_id, fake, code="scope_1_emissions", **kwargs):
    return asyncio.run(
        extract_metric(
            db_engine,
            report_id,
            code,
            2024,
            Settings(_env_file=None, ollama_model=IDENTITY.name),
            fake,
            **kwargs,
        )
    )


def test_attached_roman_footnote_does_not_change_scope_row_identity():
    source = "2024\nGlobal operations\nScope 1 GHG emissionsi\ntCO2e\n100,024\n115,294"
    result = checked(source, candidate(source, "100,024", "tCO2e"))
    assert result.can_persist
    assert "scope_value_row_mismatch" not in result.flags
    assert result.excerpt == source


def test_cached_response_reassessed_without_another_model_call(
    db_engine, saved_report, monkeypatch
):
    source = FIXTURES["clean_emissions_table"]
    report_id = saved_report([source])
    first = run(db_engine, report_id, FakeExtractor([[candidate(source)]]), top_k=1)
    monkeypatch.setattr(
        "app.extraction.service.NORMALISATION_VERSION", "test-next-rule"
    )
    fake = FakeExtractor([])
    second = run(db_engine, report_id, fake, top_k=1, resume_calls=True)
    assert not fake.calls and second["status"] == "succeeded"
    assert second["summary"]["calls"][0]["reused_from_run_id"] == first["run_id"]
    assert second["run_id"] != first["run_id"]


@pytest.mark.parametrize(
    "field",
    [
        "prompt_text",
        "chunk_sha256",
        "model_digest",
        "instruction_version",
        "schema_sha256",
    ],
)
def test_cache_requires_exact_prompt_source_model_and_schema(
    db_engine, saved_report, monkeypatch, field
):
    source = FIXTURES["clean_emissions_table"]
    report_id = saved_report([source])
    first = run(db_engine, report_id, FakeExtractor([[candidate(source)]]), top_k=1)
    with Session(db_engine) as session, session.begin():
        saved = session.get(ExtractionRun, UUID(first["run_id"]))
        summary = dict(saved.output_summary)
        summary["calls"] = [{**summary["calls"][0], field: "mismatched-cache-evidence"}]
        saved.output_summary = summary
    monkeypatch.setattr(
        "app.extraction.service.NORMALISATION_VERSION", "test-next-rule"
    )
    fake = FakeExtractor([[candidate(source)]])
    second = run(db_engine, report_id, fake, top_k=1, resume_calls=True)
    assert len(fake.calls) == 1
    assert "reused_from_run_id" not in second["summary"]["calls"][0]


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"raw_value": "999"},
        {"document_sha256": "f" * 64},
        {"year_excerpt": "2023"},
        {"unit_excerpt": "invented unit"},
    ],
)
def test_fact_review_checks_exact_source_and_never_admits_peers(
    db_engine, saved_report, tmp_path, change
):
    from app.extraction.review import review_facts

    source = FIXTURES["clean_emissions_table"]
    report_id = saved_report([source])
    body = b"%PDF-1.7\nFictional unit-test bytes, not a real company report"
    artifact = tmp_path / "test.pdf"
    artifact.write_bytes(body)
    checksum = sha(body.decode())
    with Session(db_engine) as session, session.begin():
        report = session.get(Report, report_id)
        report.source_policy = "official"
        report.content_sha256 = checksum
        report.storage_key = "test.pdf"
        parsed = session.scalar(
            select(ExtractionRun).where(ExtractionRun.report_id == report_id)
        )
        parsed.input_sha256 = checksum
    result = run(db_engine, report_id, FakeExtractor([[candidate(source)]]), top_k=1)
    observation_id = result["summary"]["observation_ids"][0]
    payload = {
        "observation_id": observation_id,
        "document_sha256": checksum,
        "metric_id": "scope_1_emissions",
        "reporting_year": 2024,
        "source_page": 1,
        "raw_value": "12,500",
        "raw_unit": "kg CO2e",
        "year_excerpt": "2024",
        "unit_excerpt": "kg CO2e",
        "review_note": "Fictional fixture row, year and unit checked; this is not an actual company claim.",
        **change,
    }
    path = tmp_path / "fact-review.json"
    path.write_text(json.dumps([payload]))
    config = Settings(_env_file=None, reports_root=tmp_path)
    if change:
        with pytest.raises(ValueError):
            review_facts(db_engine, config, path)
        return
    assert (
        review_facts(db_engine, config, path)[0]["status"]
        == "fact_validated_comparability_unchanged"
    )
    assert review_facts(db_engine, config, path)[0]["status"] == "unchanged"
    with Session(db_engine) as session:
        row = session.get(MetricObservation, observation_id)
        assert row.raw_value == "12,500" and row.normalised_value == Decimal("12.5")
        assert (
            row.validation_state == "validated"
            and row.compatibility_state == "unchecked"
        )
        event = session.scalar(
            select(ValidationEvent)
            .where(ValidationEvent.metric_observation_id == row.id)
            .order_by(ValidationEvent.created_at.desc())
        )
        assert event.actor_type == "rule" and event.details["human_signoff"] is False


def test_pipeline_persists_provenance_event_and_idempotent_model_digest(
    db_engine, saved_report
):
    source = FIXTURES["clean_emissions_table"]
    report_id = saved_report([source])
    fake = FakeExtractor([[candidate(source)]])
    result = run(db_engine, report_id, fake)
    assert (
        result["status"] == "succeeded" and result["summary"]["observation_count"] == 1
    )
    assert (
        run(db_engine, report_id, fake)["status"] == "unchanged"
        and len(fake.calls) == 1
    )
    with Session(db_engine) as session:
        provenance = observation_provenance(session)
        assert len(provenance) == 1
        assert (
            provenance[0]["raw_value"] == "12,500"
            and provenance[0]["raw_unit"] == "kg CO2e"
        )
        assert Decimal(provenance[0]["normalised_value"]) == Decimal("12.5")
        assert provenance[0]["model_digest"] == IDENTITY.digest
        assert provenance[0]["document_sha256"] == "c" * 64
        assert provenance[0]["supporting_excerpt"] == source.strip()
        assert session.scalar(select(func.count()).select_from(ValidationEvent)) == 1


def test_pipeline_missing_candidates_calls_no_model_and_never_writes_zero(
    db_engine, saved_report
):
    report_id = saved_report(["Biodiversity restoration programme during 2024."])
    fake = FakeExtractor([])
    result = run(db_engine, report_id, fake)
    assert result["summary"]["retrieval_outcome"] == "no_candidates_needs_review"
    assert result["summary"]["observation_count"] == 0 and not fake.calls


def test_pipeline_conflicting_same_passage_retains_both(db_engine, saved_report):
    source = "\n".join(FIXTURES["conflicting_values"])
    report_id = saved_report([source])
    result = run(
        db_engine,
        report_id,
        FakeExtractor(
            [[candidate(source, "120", "tCO2e"), candidate(source, "125", "tCO2e")]]
        ),
    )
    assert result["summary"]["observation_count"] == 2
    with Session(db_engine) as session:
        observations = list(session.scalars(select(MetricObservation)))
        assert {o.raw_value for o in observations} == {"120", "125"}
        assert {o.validation_state for o in observations} == {"needs_review"}


def test_pipeline_failed_call_keeps_audit_not_fabricated_observation(
    db_engine, saved_report
):
    source = FIXTURES["clean_emissions_table"]
    report_id = saved_report([source])
    result = run(db_engine, report_id, FakeExtractor([ExtractionError("timeout")]))
    assert result["status"] == "failed" and result["summary"]["observation_count"] == 0
    assert result["summary"]["calls"][0]["error_code"] == "timeout"
    assert result["summary"]["calls"][0]["prompt_text"]


def test_pipeline_invalid_citation_stays_in_audit(db_engine, saved_report):
    source = FIXTURES["clean_emissions_table"]
    report_id = saved_report([source])
    result = run(
        db_engine, report_id, FakeExtractor([[candidate(source, reported_value="999")]])
    )
    assert result["summary"]["observation_count"] == 0
    assert (
        "value_not_in_excerpt" in result["summary"]["assessments"][0]["quality_flags"]
    )


def test_year_header_outside_quote_is_retained_but_requires_review():
    source = FIXTURES["multi_year_table"]
    quote = "Scope 1 emissions | tCO2e | 140 | 130 | 120"
    result = checked(source, candidate(quote, "120", "tCO2e"))
    assert result.can_persist and result.state == "needs_review"
    assert "year_context_outside_excerpt" in result.flags
    assert "multi_year_alignment_requires_review" in result.flags
    assert not checked(quote, candidate(quote, "120", "tCO2e")).can_persist


def test_other_metric_number_cannot_be_attached_to_requested_water_metric():
    source = "2024 Global operations Total waste: 123 m3."
    result = checked(
        source, candidate(source, "123", "m3", "water_withdrawal"), "water_withdrawal"
    )
    assert not result.can_persist and "metric_context_not_in_excerpt" in result.flags


def test_unknown_unit_and_boundary_cannot_produce_comparable_value():
    source = "2024 Scope 1 emissions: 123 buckets."
    result = checked(source, candidate(source, "123", "buckets", boundary=None))
    assert result.can_persist and result.state == "needs_review"
    assert result.normalised_value is None
    assert {"boundary_unknown", "unknown_or_incompatible_unit"}.issubset(result.flags)


def test_scope2_methods_stay_distinct_and_scope3_subcategory_is_reviewed():
    source = "2024 Global operations Scope 2 location-based emissions: 123 tCO2e."
    wrong_method = checked(
        source,
        candidate(source, "123", "tCO2e", "scope_2_market_based"),
        "scope_2_market_based",
    )
    assert not wrong_method.can_persist
    source = "2024 Global operations Scope 3 emissions category 1 purchased goods: 123 tCO2e."
    result = checked(
        source,
        candidate(source, "123", "tCO2e", "scope_3_emissions"),
        "scope_3_emissions",
    )
    assert (
        result.state == "needs_review"
        and "scope3_partial_categories_possible" in result.flags
    )


def test_pipeline_intensity_denominator_and_target_routing(db_engine, saved_report):
    source = FIXTURES["intensity_only"]
    report_id = saved_report([source])
    result = run(
        db_engine,
        report_id,
        FakeExtractor(
            [[candidate(source, "2.5", "kg CO2e per unit", "emissions_intensity")]]
        ),
        code="emissions_intensity",
    )
    assert result["summary"]["persisted_states"] == {"not_comparable": 1}
    source = "2024 Global operations Net zero target year is 2050."
    report_id = saved_report([source])
    result = run(
        db_engine,
        report_id,
        FakeExtractor([[candidate(source, "2050", "year", "net_zero_target_year")]]),
        code="net_zero_target_year",
    )
    assert result["summary"]["observation_count"] == 0


def test_failure_does_not_promote_partial_results(db_engine, saved_report):
    source = FIXTURES["clean_emissions_table"]
    report_id = saved_report([source, source])
    result = run(
        db_engine,
        report_id,
        FakeExtractor([[candidate(source)], ExtractionError("malformed_json")]),
    )
    assert result["status"] == "failed" and result["summary"]["observation_count"] == 1
    assert result["summary"]["persisted_states"] == {"needs_review": 1}
    assert (
        "incomplete_candidate_run"
        in result["summary"]["assessments"][0]["quality_flags"]
    )


def test_cancelled_call_retains_prompt_and_safe_status(db_engine, saved_report):
    class CancelledExtractor(FakeExtractor):
        async def extract_structured(self, prompt, schema):
            raise asyncio.CancelledError()

    report_id = saved_report([FIXTURES["clean_emissions_table"]])
    with pytest.raises(asyncio.CancelledError):
        run(db_engine, report_id, CancelledExtractor([]))
    with Session(db_engine) as session:
        saved = session.scalar(
            select(ExtractionRun).where(ExtractionRun.stage == "extraction")
        )
        assert saved.status == "cancelled" and saved.finished_at is not None
        assert saved.output_summary["calls"][0]["error_code"] == "cancelled"
        assert session.scalar(select(func.count()).select_from(MetricObservation)) == 0


def test_status_preserves_historical_pipeline_versions(db_engine, saved_report):
    source = FIXTURES["clean_emissions_table"]
    result = run(
        db_engine, saved_report([source]), FakeExtractor([[candidate(source)]])
    )
    with Session(db_engine) as session:
        from uuid import UUID

        saved = session.get(ExtractionRun, UUID(result["run_id"]))
        saved.code_version = "metric-extraction-v0"
        session.commit()
    args = argparse.Namespace(command="extraction-status", run=None, limit=100)
    result = asyncio.run(execute(args, Settings(_env_file=None), db_engine))
    assert len(result["runs"]) == len(result["observations"]) == 1


def test_cli_retrieval_never_invokes_model(db_engine, saved_report, monkeypatch):
    class NoModel:
        async def model_identity(self):
            raise AssertionError("Retrieval must not contact Ollama")

    monkeypatch.setattr(
        "app.extraction.cli.create_extractor", lambda settings: NoModel()
    )
    report_id = saved_report([FIXTURES["clean_emissions_table"]])
    args = argparse.Namespace(
        command="retrieve-metrics",
        report=[report_id],
        metric=["scope_1_emissions"],
        year=2024,
        top_k=1,
        limit=20,
    )
    result = asyncio.run(execute(args, Settings(_env_file=None), db_engine))
    assert result["metric_jobs"] == 1 and len(result["outcomes"][0]["candidates"]) == 1
    assert not result["observations"]


def test_existing_output_path_is_not_overwritten_or_processed(tmp_path):
    target = tmp_path / "existing.json"
    target.write_text("original")
    with pytest.raises(FileExistsError):
        run_command(argparse.Namespace(output=target), Settings(_env_file=None), None)
    assert target.read_text() == "original"


def test_whole_table_quote_cannot_turn_combined_total_into_scope2():
    source = "2024 Global operations\n(Market based) GHG emissions\n1,000 tonnes CO₂e\n13,291\nDirect emissions (Scope 1)\n1,000 tonnes CO₂e\n3,733\nIndirect emissions (Scope 2)\n1,000 tonnes CO₂e\n9,558"
    wrong = checked(
        source,
        candidate(source, "13,291", "1,000 tonnes CO₂e", "scope_2_market_based"),
        "scope_2_market_based",
    )
    assert not wrong.can_persist and "scope_value_row_mismatch" in wrong.flags
    correct = checked(
        source,
        candidate(source, "9,558", "1,000 tonnes CO₂e", "scope_2_market_based"),
        "scope_2_market_based",
    )
    assert correct.can_persist and correct.normalised_value == Decimal("9558000")


def test_electricity_row_requires_its_consumption_parent_context():
    source = (
        "Energy consumption at business sites\n2023\n2024\nElectricity\nGWh\n10\n20"
    )
    c = candidate(
        "Electricity\nGWh\n10\n20",
        "20",
        "GWh",
        "electricity_consumption",
        boundary=None,
    )
    result = checked(source, c, "electricity_consumption")
    assert result.can_persist and result.state == "needs_review"
    assert result.normalised_value == Decimal("72000")
    assert not checked(
        source.replace("Energy consumption at business sites", "Energy generation"),
        c,
        "electricity_consumption",
    ).can_persist


def test_scope_recheck_rejects_legacy_mismatch_and_preserves_original_evidence(
    db_engine, saved_report
):
    source = "2024 Global operations\n(Market based) GHG emissions\n1,000 tonnes CO₂e\n13,291\nIndirect emissions (Scope 2)\n1,000 tonnes CO₂e\n9,558"
    report_id = saved_report([source])
    run(
        db_engine,
        report_id,
        FakeExtractor(
            [[candidate(source, "9,558", "1,000 tonnes CO₂e", "scope_2_market_based")]]
        ),
        code="scope_2_market_based",
    )
    with Session(db_engine) as session:
        observation = session.scalar(select(MetricObservation))
        # Simulate the earlier broad-quote rule, solely in an isolated fixture.
        observation.raw_value = "13,291"
        observation.normalised_value = Decimal("13291000")
        session.commit()
    result = recheck_scope_rows(db_engine)
    assert result["checked"] == result["rejected"] == 1 and result["model_calls"] == 0
    assert recheck_scope_rows(db_engine)["checked"] == 0
    with Session(db_engine) as session:
        observation = session.scalar(select(MetricObservation))
        assert (
            observation.validation_state == "rejected"
            and observation.raw_value == "13,291"
        )
        assert (
            observation.supporting_excerpt == source
            and observation.normalised_value is None
        )
        event = session.scalar(
            select(ValidationEvent).where(
                ValidationEvent.rule_code == "scope_row_recheck"
            )
        )
        assert Decimal(
            event.details["previous_conversion_and_confidence"]["normalised_value"]
        ) == Decimal("13291000")
