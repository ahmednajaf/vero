import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KnowledgeAnswer
from app.knowledge.explanation import ExplainRequest, explain, explanation_records, model_records
from app.knowledge.provider import Completion, ResearchError
from app.knowledge.publication import Chapter
from app.knowledge.publication import ground_chapter
from test_publication import sample_payload
from test_report_synthesis import assemble, ReportSynthesis, proposal, packet
from test_openai_extraction import settings


def payload():
    data = sample_payload()
    data['id'] = str(uuid4())
    data['definition']['company_ids'] = [c['id'] for c in data['definition']['companies']]
    data['sections'].append({'id':'derive:fixture','kind':'derive','title':'Calculation','status':'completed',
        'result':assemble(ReportSynthesis(insights=[],awards=[proposal()]),packet())})
    return data


def test_explanation_packet_preserves_calculations_and_source_links():
    data = payload()
    records = explanation_records(data)
    assert any(r.get('calculation') for r in records.values())
    chosen = model_records(records, 'Explain the calculated emissions', 100000)
    for key, record in chosen.items():
        assert {c['quote'] for c in record['citations']} == {c['quote'] for c in records[key]['citations']}
        assert 'evidence_id' not in record['citations'][0]
    assert model_records(records, 'Question', 1) == {}


def test_source_order_does_not_invalidate_explanation_cache():
    from test_report_synthesis import sources
    refs=list(sources().values())
    a={'C1':{'text':'A calculated comparison','citations':refs}}
    b={'C1':{'text':'A calculated comparison','citations':list(reversed(refs))}}
    assert model_records(a,'comparison') == model_records(b,'comparison')


class Provider:
    calls = 0

    async def structured(self, payload, schema, instructions):
        self.calls += 1
        packet = json.loads(payload['source_extraction_task'])
        key, record = next((k,r) for k,r in packet['records'].items() if r.get('calculation'))
        row = record['calculation']['rows'][0]
        output = Chapter(paragraphs=[dict(heading='Calculated comparison',takeaway='The saved calculation connects the inputs.',
            text=f"The calculated result is {float(row['value']):.3f} {row['unit']} for {row['company']}.",record_ids=[key])])
        return Completion(output, 200, 80, 15, 'fixture-mini')


def test_live_adapter_and_cached_explanation_reuse_saved_inputs(db_engine):
    data, provider = payload(), Provider()
    request = ExplainRequest(question='Explain the calculated comparison')
    first = asyncio.run(explain(db_engine, data, request, settings(), provider))
    second = asyncio.run(explain(db_engine, data, request, settings(), provider))
    assert first['claims'] and first['model_called']
    assert second['cached'] and not second['model_called'] and provider.calls == 1
    assert first['claims'][0]['citations'][0]['page']
    assert first['analysis_id'] == data['id']
    with Session(db_engine) as db:
        ledger = db.scalar(select(KnowledgeAnswer))
        assert ledger.payload['structured_result'] and ledger.payload['claims']
        assert ledger.question == request.question and ledger.charged_usd > 0


def test_unsupported_contextual_number_is_not_published(db_engine):
    class BadProvider(Provider):
        async def structured(self, *args):
            result = await super().structured(*args)
            result.data.paragraphs[0].text = 'The calculated result is 999999999%.'
            return result
    with pytest.raises(ResearchError, match='grounding_failed'):
        asyncio.run(explain(db_engine, payload(), ExplainRequest(question='Explain this result'), settings(), BadProvider()))


def test_formula_constants_can_be_explained_without_becoming_reported_values():
    from test_report_synthesis import sources
    records={'C1':{'citations':[sources()['S1']], 'calculation':{'steps':[{'operation':'subtract','operands':['female','0']}], 'rows':[{'value':'-8.4','unit':'hours','year':2026,'inputs':[]}]}}}
    output=Chapter(paragraphs=[{'heading':'Calculation reference','takeaway':'Zero is the comparison reference.',
        'text':'The mathematical reference value is 0. The calculated gap is -8.4 hours in 2026.', 'record_ids':['C1']}])
    assert ground_chapter(output,records)['status']=='answered'
    output.paragraphs[0].text='The mathematical reference value is 12345.'
    with pytest.raises(ResearchError,match='grounding_failed'):
        ground_chapter(output,records)
