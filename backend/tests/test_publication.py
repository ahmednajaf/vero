"""Offline package-generation acceptance tests. Synthetic fixtures never enter app data."""
import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import pymupdf
import pytest
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.knowledge.briefings import BriefingRequest, create, advance
from app.knowledge.publication import Chapter, document, editorial_stages, ground_chapter, packets, records_for, research_stages
from app.knowledge.report_exports import html, pdf
from app.knowledge.synthesis import ReportSynthesis, assemble, award_result
from app.knowledge.provider import Completion, ResearchError
from app.knowledge.analysis_contract import CompanyEvidence, PeerAnalysis, FindingReview
from test_report_synthesis import COMPANIES, packet, proposal, sections, sources, value
from test_knowledge import corpus, MockProvider, ai_settings  # noqa: F401


def test_company_and_sector_contracts_are_distinct():
    identifiers = [uuid4() for _ in range(20)]
    assert len(BriefingRequest(primary_company_id=identifiers[0], peer_ids=identifiers[1:], package="sector").peer_ids) == 19
    with pytest.raises(ValidationError):
        BriefingRequest(primary_company_id=identifiers[0], peer_ids=identifiers[1:], package="company")
    stages = research_stages({"energy": "Energy", "people": "People"}, list(map(str, identifiers)))
    assert len(stages) == 17  # 2 topics x 4 company batches x 2 research lenses + compilation.
    for topic in ("energy", "people"):
        assert {i for s in stages if s.get("topic_id") == topic for i in s["company_ids"]} == set(map(str, identifiers))


def test_all_findings_are_partitioned_without_a_ten_insight_limit():
    items = sections()
    items[0]["result"]["claims"] *= 20
    for i, claim in enumerate(items[0]["result"]["claims"]):
        items[0]["result"]["claims"][i] = {**claim, "text": f"Distinct finding {i}: " + claim["text"]}
    result = packets({"companies": COMPANIES}, items, 900)
    assert len(result) > 1
    assert sum(len(r["packet"]["findings"]) for r in result) == 40
    assert all(r["packet"]["omitted_findings"] == 0 for r in result)
    insight = {"headline": "Different reported totals", "observation": "The operational totals are different.", "implication": "Investigate scale and operating mix.", "source_ids": ["S1", "S2"]}
    assert len(ReportSynthesis(insights=[insight] * 23, awards=[proposal()] * 7).insights) == 23


def test_oversized_single_finding_fails_explicitly_not_silently_omitted():
    with pytest.raises(ResearchError, match="packet_too_large"):
        packets({"companies": COMPANIES}, sections(), 1)


def test_derived_values_can_be_explained_and_invented_values_cannot():
    p = proposal(operation="percent_change", denominator_unit="tCO2e", entrants=[
        {"company_id": "a", "numerator": value("2", "MtCO2e", "S1"), "denominator": value("2.5", "MtCO2e", "S1", 2024)},
        {"company_id": "b", "numerator": value("1500", "ktCO2e", "S2"), "denominator": value("2000", "ktCO2e", "S2", 2024)},
    ])
    records = records_for(assemble(ReportSynthesis(insights=[], awards=[p]), packet()))
    output = Chapter(paragraphs=[{"heading": "Reported reduction", "takeaway": "Fixture B reports a reduction.", "text": "Fixture B's calculated emissions change is -25%.", "record_ids": ["C1"]}])
    assert ground_chapter(output, records)["paragraphs"][0]["citations"]
    output.paragraphs[0].text = "Fixture B's calculated emissions change is -99%."
    with pytest.raises(ResearchError, match="grounding_failed"):
        ground_chapter(output, records)
    output.paragraphs[0].record_ids = ["invented"]
    with pytest.raises(ResearchError, match="grounding_failed"):
        ground_chapter(output, records)


def test_common_unit_inputs_match_exported_formula():
    p = proposal(operation="difference", denominator_unit="ktCO2e", entrants=[
        {"company_id": "a", "numerator": value("2", "MtCO2e", "S1"), "denominator": value("2", "MtCO2e", "S1")},
        {"company_id": "b", "numerator": value("1500", "ktCO2e", "S2"), "denominator": value("1500", "ktCO2e", "S2")},
    ])
    result = award_result(p, sources(), COMPANIES)
    assert result["rows"][0]["inputs"][1]["unit"] == "tCO2e"
    assert float(result["rows"][0]["value"]) == 0


def test_editorial_unit_scaling_and_signed_reduction_are_not_new_facts():
    records={'change':dict(citations=[sources()['S1']], calculation=dict(rows=[dict(value='-3.498542274',unit='%',
        inputs=[dict(value='33100000',raw_value='33,100,000'),dict(value='34300000',raw_value='34,300,000')])]))}
    paragraph=dict(heading='Emissions movement',takeaway='Emissions fell in the reported period.',
        text='Emissions fell 3.5%, from 34.3 to 33.1 million tonnes.',record_ids=['change'])
    assert ground_chapter(Chapter(paragraphs=[paragraph]),records)['paragraphs']
    paragraph['text']='Emissions fell 99%, from 34.3 to 33.1 million tonnes.'
    with pytest.raises(ResearchError,match='grounding_failed'):
        ground_chapter(Chapter(paragraphs=[paragraph]),records)


def test_writer_may_use_the_same_bounded_source_context_it_received():
    records={'target':dict(citations=[{**sources()['S1'], 'quote':'The target was achieved.',
        'text':'The target was achieved. The reported achievement year was 2019.'}])}
    paragraph=dict(heading='Delivery before deadline',takeaway='The report records an achieved target.',
        text='The target was achieved in 2019.',record_ids=['target'])
    assert ground_chapter(Chapter(paragraphs=[paragraph]),records)['paragraphs']


def test_written_percent_and_table_header_year_use_grounded_fact_fields():
    record={'f':{'citations':[{**sources()['S1'],'quote':'Female employees 35'}],
                 'reported_values':[dict(metric='Women in workforce',value='35',unit='%',year=2025)]}}
    paragraph=dict(heading='Workforce representation',takeaway='The reported workforce share.',
                   text='Women accounted for 35% of the workforce in 2025.',record_ids=['f'])
    assert ground_chapter(Chapter(paragraphs=[paragraph]),record)['paragraphs']
    paragraph['text']='Women accounted for 99% of the workforce in 2025.'
    with pytest.raises(ResearchError,match='grounding_failed'):
        ground_chapter(Chapter(paragraphs=[paragraph]),record)


def sample_payload():
    return {"id": "fixture", "title": "Peer comparison <script>", "created_at": "2026-10-13", "sources_current": True,
            "definition": {"companies": COMPANIES, "package": "company"}, "sections": sections(), "review_opportunities": []}


def test_client_exports_do_not_dump_excerpts_and_link_sources():
    payload = sample_payload()
    rendered = html(payload)
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert sources()["S1"]["quote"] not in rendered
    assert "#page=12" in rendered
    result = pdf(payload)
    with pymupdf.open(stream=result, filetype="pdf") as parsed:
        text = " ".join(p.get_text() for p in parsed)
        assert len(parsed) >= 4
        assert "physical page 12" in text and "Fixture annual report" in text
        assert "2024: 2.5 MtCO2e" not in text
        assert any(page.get_links() for page in parsed)


def test_unfinished_exports_are_explicitly_marked_as_working_drafts():
    payload = sample_payload()
    payload['sections'].append({'id': 'pending', 'title': 'Pending chapter', 'status': 'pending', 'result': None})
    assert document(payload)['incomplete']
    assert 'Working draft' in html(payload)
    with pymupdf.open(stream=pdf(payload), filetype='pdf') as parsed:
        assert 'ANALYSIS INCOMPLETE' in parsed[0].get_text()


def test_document_deduplicates_research_and_uses_authored_chapters():
    payload = sample_payload()
    payload["sections"][0].update(kind="research", topic_id="emissions")
    payload["sections"].append({"id": "chapter:0", "kind": "chapter", "topic_id": "emissions", "title": "Emissions", "result": {"paragraphs": [{"heading": "Reported difference", "text": "A written comparison of the reported operational footprint.", "citations": [sources()["S1"]]}]}})
    doc = document(payload)
    assert doc["authored"] and len(doc["chapters"]) == 1 and doc["findings_count"] == 1
    payload["sections"].append({"id": "chapter:1", "kind": "chapter", "topic_id": "emissions", "title": "Emissions", "result": None})
    partial = document(payload)
    assert len(partial["chapters"]) == 1  # Same heading is one readable chapter.
    assert len(partial["chapters"][0]["paragraphs"]) == 3  # Unwritten research is still available.


def test_publication_keeps_one_written_edition_per_record_without_a_finding_quota():
    payload = sample_payload()
    def paragraph(text, refs):
        return dict(heading=text, text=text, record_ids=refs, citations=[sources()['S1']])
    payload['sections'] = [
        dict(id='publish:first',kind='publish',title='First',result=dict(paragraphs=[
            paragraph('Original analysis', ['finding']),
            paragraph('Additional company detail in the same chapter', ['finding']),
        ])),
        dict(id='publish:rewrite',kind='publish',title='Rewrite',result=dict(paragraphs=[
            paragraph('A differently worded repeat of the same record', ['finding']),
            paragraph('A genuinely different analytical record', ['another-finding']),
        ])),
    ]
    doc = document(payload)
    assert doc['findings_count'] == 3
    assert [p['text'] for c in doc['chapters'] for p in c['paragraphs']] == [
        'Original analysis', 'Additional company detail in the same chapter',
        'A genuinely different analytical record',
    ]
    assert len(payload['sections'][1]['result']['paragraphs']) == 2  # Audit untouched.


class PackageProvider(MockProvider):
    def __init__(self):
        super().__init__()
        self.structured_calls = 0

    async def structured(self, payload, schema, instructions):
        self.structured_calls += 1
        data = json.loads(payload["source_extraction_task"])
        if schema is CompanyEvidence:
            ref, source = next(iter(data['evidence'].items()))
            result = CompanyEvidence(facts=[dict(id='reported',metric='Reported programme',value='programme',unit=None,year=None,population='company',kind='activity',source_id=ref,excerpt=source['text'][:300])],promises=[],disclosures=[],research_requests=[])
        elif schema is PeerAnalysis:
            ref = data['company_evidence'][0]['facts'][0]['id']
            result = PeerAnalysis(analysis_title='Reported implementation differences',executive_questions=[],derived_metrics=[],findings=[dict(id='f1',headline='Reported implementation differences',takeaway='Companies describe different implementation approaches.',explanation='The company describes its programme.',business_implication='Compare the implementation approaches.',fact_ids=[ref],metric_ids=[],counterpoint='',priority='lead')],awards=[],report_outline=[dict(heading='Implementation',question='What is different?',finding_ids=['f1'],metric_ids=[],award_ids=[])],research_requests=[])
        elif schema is FindingReview:
            result = FindingReview(checks=[dict(finding_id=f['id'],outcome='unchanged',reason='Consistent with fixture evidence.',correction=None) for f in data['findings']])
        elif schema is ReportSynthesis:
            ref = next(iter(data["sources"]))
            result = ReportSynthesis(insights=[{"headline": "Supplier training is reported", "observation": "The company describes a supplier training programme.", "implication": "A useful starting point for examining implementation.", "source_ids": [ref]}], awards=[])
        else:
            result = Chapter(paragraphs=[{"heading": "Supplier engagement", "takeaway": "A supplier training programme is reported.", "text": "The reported supplier training programme provides a basis for comparing implementation approaches.", "record_ids": [next(iter(data["records"]))]}])
        return Completion(result, 100, 100, 20, "fixture-model")


@pytest.mark.parametrize("package", ["company", "sector"])
def test_package_runs_resume_and_export_with_no_extra_model_call(db_engine, corpus, package):
    _, ids = corpus
    provider = PackageProvider()
    with Session(db_engine) as session:
        row = create(session, BriefingRequest(primary_company_id=ids[0][0], peer_ids=[ids[1][0]], topics=["supply_chain"], package=package))
        assert len(row.sections) == 5  # Research and gap checks per company, then analysis.
        for _ in range(12):
            result = asyncio.run(advance(session, row.id, ai_settings(), provider))
            assert result["status"] != "failed", result["sections"]
            if not result["can_resume"]:
                break
        assert not result["can_resume"] and provider.structured_calls >= 2
        written = [s['result'] for s in result['sections'] if s.get('kind') == 'publish']
        assert written and all(s['publication_method'] == 'assembled_from_saved_ai_analysis' for s in written)
        assert len(result["matrix"]) == 0
        assert document(result)["authored"]
        calls = provider.calls + provider.structured_calls
        pdf(result)
        html(result)
        asyncio.run(advance(session, row.id, ai_settings(), provider))
        assert provider.calls + provider.structured_calls == calls


def test_export_pdf_endpoint_is_read_only(api_client, corpus):
    _, ids = corpus
    result = api_client.post('/api/knowledge/briefings', json={"primary_company_id": str(ids[0][0])}).json()
    response = api_client.get(f"/api/knowledge/briefings/{result['id']}/export?format=pdf")
    assert response.status_code == 200 and response.content.startswith(b'%PDF')


def test_saved_trial_budget_applies_when_resuming_with_normal_settings(db_engine, corpus):
    from datetime import UTC, datetime
    _, ids = corpus
    provider = PackageProvider()
    with Session(db_engine) as session:
        row = create(session, BriefingRequest(primary_company_id=ids[0][0], topics=['supply_chain']))
        row.definition = {**row.definition, 'trial_spending_ceiling': '0.000001',
                          'trial_month': datetime.now(UTC).strftime('%Y-%m')}
        session.commit()
        result = asyncio.run(advance(session, row.id, ai_settings(), provider))
        assert result['status'] == 'paused'
        assert result['sections'][0]['error_code'] == 'trial_budget_exceeded'
        assert provider.structured_calls == 0
