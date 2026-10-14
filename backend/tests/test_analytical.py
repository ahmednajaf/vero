"""Isolated synthetic tests for the executable analytical brief; no live AI calls."""
from copy import deepcopy
from decimal import Decimal

import pytest

from app.knowledge.analysis_contract import CompanyEvidence, Metric, PeerAnalysis
from app.knowledge.analytical import assemble, calculate, chapter_stages, collection_batches, collection_summary, disclosure_scores, grounded_ledger, master, merge_ledgers, model_evidence
from app.knowledge.analytical import fact_aliases, resolve_fact_aliases, compact_sources, stages
from app.knowledge.analytical import namespace_records, records
from app.knowledge.publication import document
from app.knowledge.provider import ResearchError
from test_report_synthesis import sources


def facts():
    result = {}
    for company, values in [('a', ('30', '60', '2')), ('b', ('40', '80', '4'))]:
        for name, value in zip(('leaders', 'workforce', 'hours'), values):
            result[f'{company}:{name}'] = {'id': f'{company}:{name}', 'company_id': company, 'metric': name,
                'value': value, 'unit': '%' if name != 'hours' else 'hours', 'year': 2025, 'kind': 'actual',
                'source': {**sources()['S1'], 'quote': f'2025 workforce 60% and 80%, leadership 30% and 40%, training 2 hours and 4 hours.'}}
    return result


def metric(**changes):
    data = dict(id='representation', name='Leadership representation', question='Does representation reach leadership?',
        definition='Leadership share relative to workforce share', formula='100 * leaders / workforce',
        steps=[{'id': 'relative', 'operation': 'divide', 'operands': ['leaders', 'workforce']},
               {'id': 'result', 'operation': 'multiply', 'operands': ['relative', '100']}],
        result_step_id='result', result_unit='parity index', direction='near_reference', reference_value='100',
        rows=[{'company_id': c, 'inputs': [{'id': n, 'fact_id': f'{c}:{n}', 'normalised_unit': '%'} for n in ('leaders', 'workforce')]} for c in ('a','b')],
        interpretation='Closer to parity means similar representation.', scope_note='Reported employee populations.')
    return Metric(**{**data, **changes})


def output(**changes):
    return PeerAnalysis(**{**dict(analysis_title='Who reaches leadership?', executive_questions=['What changes at leadership level?'],
        derived_metrics=[metric()], findings=[dict(id='f1', headline='A leadership representation gap', takeaway='Leadership representation trails the workforce.',
        explanation='Both peers have a calculated parity index of 50.', business_implication='Examine progression into decision-making roles.',
        fact_ids=[], metric_ids=['representation'], counterpoint='Workforce mix also matters.', priority='lead')],
        awards=[dict(id='a1',name='Representation bridge',why_it_matters='Recognises the closest leadership-to-workforce representation.',basis='numeric',metric_id='representation',rubric=[],assessments=[])],
        report_outline=[dict(heading='Who reaches leadership?',question='How wide is the gap?',finding_ids=['f1'],metric_ids=['representation'],award_ids=['a1'])],research_requests=[]), **changes})


def result():
    ledgers=[{'company_id':c,'facts':[f for f in facts().values() if f['company_id']==c],'promises':[],'disclosures':{}} for c in ('a','b')]
    return assemble(output(),ledgers,{'companies':[{'id':'a','company_name':'Fixture A'},{'id':'b','company_name':'Fixture B'}]})


def test_multistep_arithmetic_ties_and_source_inputs():
    data=result()
    assert data['metrics'][0]['rows'][0]['value']=='50.0'
    assert data['badges'][0]['winner_ids']==['a','b']
    assert data['analytical_findings'][0]['citations']
    assert data['metrics'][0]['rows'][0]['inputs'][0]['raw_unit']=='%'
    assert result()==data


def test_part_whole_percentage_cannot_exceed_total_but_relative_index_can():
    data = facts()
    data['a:leaders']['value'] = '120'
    m = metric(name='Scope 3 concentration in total emissions', definition='Scope 3 total as a share of total emissions', result_unit='%')
    answer = calculate(m, data, {'a':'A','b':'B'})
    assert answer['excluded'] == [dict(company_id='a',reason='part_whole_out_of_range')]
    assert len(answer['rows']) == 1 and answer['direction'] == 'none'
    assert len(calculate(metric(), data, {'a':'A','b':'B'})['rows']) == 2


def test_scope3_category_cannot_stand_in_for_scope3_total():
    data = facts()
    data['a:leaders']['metric'] = 'Scope 3 Category 11 emissions'
    m = metric(name='Scope 3 concentration in total emissions', definition='Reported Scope 3 total as a share of total emissions', result_unit='%')
    answer = calculate(m, data, {'a':'A','b':'B'})
    assert answer['excluded'] == [dict(company_id='a',reason='category_is_not_scope3_total')]


def test_annual_financial_return_cannot_use_undated_initiative_funding():
    data = facts()
    for fact in data.values():
        fact['unit'] = 'USD'
    data['a:workforce']['year'] = None
    m = metric(name='Technology return on investment', definition='Realised value divided by investment in the period')
    for row in m.rows:
        for i in row.inputs:
            i.normalised_unit = 'USD'
    answer = calculate(m, data, {'a':'A','b':'B'})
    assert answer['excluded'] == [dict(company_id='a',reason='financial_ratio_period_missing')]
    assert [r['company_id'] for r in answer['rows']] == ['b']


def test_mixed_reporting_bases_keep_values_without_a_rank_or_award():
    m = metric(scope_note='Each company reports a different emissions boundary or accounting basis.')
    answer = calculate(m, facts(), {'a':'A','b':'B'})
    assert len(answer['rows']) == 2
    assert answer['contextual'] and answer['direction'] == 'none'


def test_actual_finance_progress_can_use_a_future_target_denominator():
    data = facts()
    for fact in data.values():
        fact['unit'] = 'USD'
    for c in ('a','b'):
        data[f'{c}:workforce'].update(kind='target',year=2030)
    m = metric(name='Delivered financing as share of target', result_unit='%')
    for row in m.rows:
        for operand in row.inputs:
            operand.normalised_unit = 'USD'
    answer = calculate(m,data,{'a':'A','b':'B'})
    assert not answer['excluded']
    assert [r['year'] for r in answer['rows']] == [2025,2025]


@pytest.mark.parametrize('note', ['Not a like-for-like ranking.', 'Different operational boundaries.', 'Each company discloses a different leadership population label.'])
def test_contextual_scope_notes_preserve_values_without_awards(note):
    answer = calculate(metric(scope_note=note), facts(), {'a':'A','b':'B'})
    assert len(answer['rows']) == 2
    assert answer['contextual'] and answer['direction'] == 'none'


def test_omitted_formula_repair_preserves_valid_peer_rows():
    from app.knowledge.analytical import best_repair
    data = facts()
    del data['b:leaders']
    repaired = best_repair(metric(), None, data, {'a':'A','b':'B'})
    assert [r.company_id for r in repaired.rows] == ['a']
    assert calculate(repaired, data, {'a':'A','b':'B'})['rows'][0]['value'] == '50.0'


def test_valid_correction_takes_precedence_over_larger_original_sample():
    from app.knowledge.analytical import best_repair
    correction = metric(scope_note='Corrected definition', rows=metric().rows[:1])
    repaired = best_repair(metric(), correction, facts(), {'a':'A','b':'B'})
    assert repaired.scope_note == 'Corrected definition'
    assert len(repaired.rows) == 1


def test_formula_repair_evidence_retains_references_and_balances_companies():
    from app.knowledge.analytical import repair_evidence
    ledgers = [{'company_id':c,'facts':[f for f in facts().values() if f['company_id']==c]} for c in ('a','b')]
    selected = repair_evidence(metric().model_dump(), ledgers)
    assert {l['company_id'] for l in selected} == {'a','b'}
    for ledger in selected:
        assert {f['id'] for f in ledger['facts']} >= {f"{ledger['company_id']}:leaders",f"{ledger['company_id']}:workforce"}


def test_model_fact_retains_source_row_labels_for_ambiguous_metric_names():
    from app.knowledge.analytical import model_fact
    male = dict(id='m',metric='Employees by gender',value='400',unit='employees',source={'quote':'Male\n400\n410'})
    female = dict(id='f',metric='Employees by gender',value='600',unit='employees',source={'quote':'Female\n600\n590'})
    assert model_fact(male)['source_excerpt'].startswith('Male')
    assert model_fact(female)['source_excerpt'].startswith('Female')
    assert 'source' not in model_fact(male)


@pytest.mark.parametrize('mode', ['corrected','omitted','rejected'])
def test_focused_formula_review_keeps_aliases_and_distinguishes_rejection(db_engine, monkeypatch, mode):
    import asyncio
    import json
    from types import SimpleNamespace
    from app.core.config import Settings
    from app.knowledge.analysis_contract import MetricRepairs
    from app.knowledge.analytical import repair_metrics
    calls = []
    class MockExtractor:
        def __init__(self, *args, **kwargs):
            pass
        async def extract_structured(self, prompt, schema):
            packet = json.loads(prompt.text)
            calls.append(packet)
            assert len(packet['corrections']) == 1
            proposal = packet['corrections'][0]['proposal']
            value = MetricRepairs(derived_metrics=[Metric(**proposal)] if mode == 'corrected' else [],
                rejected_ids=[proposal['id']] if mode == 'rejected' else [])
            return SimpleNamespace(data=value,attempts=0,prompt_sha256='0'*64,latency_ms=0.0,model='fixture')
    monkeypatch.setattr('app.knowledge.analytical.OpenAIStructuredExtractor',MockExtractor)
    proposal = output()
    before = proposal.model_dump()
    ledgers = [{'company_id':c,'facts':[f for f in facts().values() if f['company_id']==c]} for c in ('a','b')]
    repaired, audit = asyncio.run(repair_metrics(proposal,ledgers,{'companies':[{'id':c,'company_name':c} for c in ('a','b')]},Settings(_env_file=None),db_engine,None))
    assert proposal.model_dump() == before
    assert len(calls) == 1 and audit['cached'] and audit['estimated_cost_usd'] == '0'
    assert len(repaired.derived_metrics[0].rows) == (0 if mode == 'rejected' else 2)
    if mode != 'rejected':
        assert repaired.derived_metrics[0].rows[0].inputs[0].fact_id == 'a:leaders'


def test_final_finding_review_keeps_accurate_text_and_requires_every_finding():
    from app.knowledge.analysis_contract import FindingReview
    from app.knowledge.analytical import apply_finding_review
    data = result()
    review = FindingReview(checks=[dict(finding_id='f1',outcome='unchanged',reason='Matches calculated result.',correction=None)])
    assert apply_finding_review(data,review,facts())['analytical_findings'] == data['analytical_findings']
    with pytest.raises(ResearchError,match='finding_review_incomplete'):
        apply_finding_review(data,FindingReview(checks=[]),facts())


def test_incomplete_finding_review_requests_only_missing_checks(db_engine, monkeypatch):
    import asyncio
    import json
    from types import SimpleNamespace
    from app.core.config import Settings
    from app.knowledge.analysis_contract import FindingReview
    from app.knowledge.analytical import review_findings
    calls = []
    class MockExtractor:
        def __init__(self, *args, **kwargs):
            pass
        async def extract_structured(self,prompt,schema):
            packet=json.loads(prompt.text)
            calls.append(packet)
            checks=[] if len(calls)==1 else [dict(finding_id='f1',outcome='unchanged',reason='Supported.',correction=None)]
            return SimpleNamespace(data=FindingReview(checks=checks),attempts=0,prompt_sha256=str(len(calls))*64,latency_ms=0.0,model='fixture')
    monkeypatch.setattr('app.knowledge.analytical.OpenAIStructuredExtractor',MockExtractor)
    ledgers=[dict(facts=list(facts().values()))]
    reviewed=asyncio.run(review_findings(result(),ledgers,Settings(_env_file=None),db_engine,None))
    assert len(calls)==2 and calls[1]['required_finding_ids']==['f1']
    assert len(reviewed['analytical_findings'])==1
    assert reviewed['finding_review']['cached']
    assert len(reviewed['finding_review']['prompt_sha256s'])==2


def test_final_finding_corrections_still_require_grounded_numbers_and_sources():
    from app.knowledge.analysis_contract import FindingReview
    from app.knowledge.analytical import apply_finding_review
    changed = output().findings[0].model_dump()
    changed['explanation'] = 'The calculated parity index is 99.'
    review = FindingReview(checks=[dict(finding_id='f1',outcome='corrected',reason='Fixture',correction=changed)])
    rejected = apply_finding_review(result(),review,facts())
    assert not rejected['analytical_findings']
    assert rejected['rejected_review_corrections'][0]['reason']=='report_editorial_grounding_failed'
    review.checks[0].correction.explanation = 'The calculated parity index is 50.'
    assert apply_finding_review(result(),review,facts())['analytical_findings'][0]['explanation'].endswith('50.')
    review.checks[0].correction.fact_ids = ['invented']
    rejected = apply_finding_review(result(),review,facts())
    assert not rejected['analytical_findings']
    assert rejected['rejected_review_corrections'][0]['reason']=='unknown_reference'


def test_rejected_finding_is_auditable_but_not_published_as_a_claim():
    from app.knowledge.analysis_contract import FindingReview
    from app.knowledge.analytical import apply_finding_review
    review = FindingReview(checks=[dict(finding_id='f1',outcome='rejected',reason='Unsupported central claim.',correction=None)])
    answer = apply_finding_review(result(),review,facts())
    assert not answer['analytical_findings'] and not answer['claims']
    assert answer['metrics']  # Evidence/calculations are not erased.


def test_numeric_peer_fact_cannot_be_attributed_to_other_company():
    from app.knowledge.analytical import ground_finding
    f=facts()
    for key,value in f.items():
        value['source']={**value['source'],'company':'Boreal Energy' if key.startswith('a:') else 'Cedar Energy'}
    proposal=output().findings[0]
    proposal.fact_ids=['b:leaders']
    proposal.metric_ids=[]
    proposal.explanation='Boreal reports 40% leadership representation.'
    proposal.headline='Representation differs'
    with pytest.raises(ResearchError,match='company_number_not_supported'):
        ground_finding(proposal,f,{})
    proposal.explanation='Cedar reports 40% leadership representation.'
    assert ground_finding(proposal,f,{})['citations']


def test_writer_never_receives_rejected_empty_calculations():
    data = result()
    data['metrics'][0]['rows'] = []
    data['badges'][0]['rows'] = []
    packet = records(data)
    assert 'representation' not in packet and 'a1' not in packet
    assert 'f1' in packet


def test_response_local_record_ids_are_namespaced_without_a_second_model_call():
    resolved = namespace_records(output(), {'representation','f1','a1'}, 'analyse:5')
    assert resolved.derived_metrics[0].id == 'analyse:5:representation'
    assert resolved.findings[0].metric_ids == ['analyse:5:representation']
    assert resolved.awards[0].metric_id == 'analyse:5:representation'
    assert resolved.report_outline[0].finding_ids == ['analyse:5:f1']
    assert resolved.report_outline[0].award_ids == ['analyse:5:a1']
    assert resolved.derived_metrics[0].rows == output().derived_metrics[0].rows


def test_long_finding_headline_does_not_crash_calculation_stage():
    proposal=output()
    proposal.findings[0].headline='Leadership representation is an important relationship. ' * 4
    proposal.findings[0].explanation='The underlying workforce and leadership populations matter. ' * 40
    ledgers=[dict(company_id=c,facts=[f for f in facts().values() if f['company_id']==c]) for c in 'ab']
    answer=assemble(proposal,ledgers,{'companies':[dict(id=c,company_name=c) for c in 'ab']})
    assert len(answer['analytical_findings'])==1


def test_formatted_numeric_fact_is_calculated_without_changing_raw_value():
    data=facts()
    data['a:leaders']['value']='3,000'
    answer=calculate(metric(),data,{'a':'A','b':'B'})
    assert answer['rows'][0]['value']=='5000'
    assert answer['rows'][0]['inputs'][0]['raw_value']=='3,000'


def test_scaled_amount_in_value_column_preserves_raw_text_and_numeric_operand():
    data = facts()
    data['a:leaders'].update(value='16.6 million', unit='hours')
    data['a:workforce'].update(value='76,664', unit='employees')
    m = metric(rows=[dict(company_id='a', inputs=[dict(id='leaders', fact_id='a:leaders', normalised_unit='hours'), dict(id='workforce', fact_id='a:workforce', normalised_unit='employees')])])
    answer = calculate(m, data, {'a':'A'})
    assert not answer['excluded']
    raw = answer['rows'][0]['inputs'][0]
    assert raw['raw_value'] == '16.6 million' and Decimal(raw['raw_numeric_value']) == 16600000


def test_expands_explicit_labelled_cells_without_inventing_percentage():
    fact = dict(id='a:workforce',company_id='a',metric='Employees by gender',value='Male 16,552; Female 7,996; Total 24,620', unit='headcount', source=dict(quote='Male 16,552 Female 7,996 Total 24,620'))
    ledger = merge_ledgers([dict(kind='collect',result=dict(company_id='a',facts=[fact]))])[0]
    assert [f['value'] for f in ledger['facts']] == [fact['value'],'16,552','7,996','24,620']
    assert ledger['facts'][2]['metric'] == 'Employees by gender / Female'


def test_sum_of_one_input_is_an_identity_not_doubled():
    m=metric(steps=[dict(id='same',operation='add',operands=['leaders']),
        dict(id='result',operation='divide',operands=['same','workforce'])])
    value=calculate(m,facts(),{'a':'A','b':'B'})
    assert value['rows'][0]['value']=='0.5'


def test_same_named_reported_and_calculated_results_are_labelled_separately():
    from app.knowledge.publication import display_metrics
    data=result()
    reported=deepcopy(data['metrics'][0])
    reported['id']='reported'
    for row in reported['rows']:
        row['inputs']=row['inputs'][:1]
        row['value']='40'
    displayed=display_metrics([dict(result=dict(metrics=[reported,*data['metrics']]))])
    assert displayed[0]['name'].endswith('· reported')
    assert displayed[1]['name'].endswith('· calculated')


def test_peer_comparison_is_presented_before_single_company_calculation():
    from app.knowledge.publication import display_metrics
    shared = result()['metrics'][0]
    solo = deepcopy(shared)
    solo.update(id='solo',name='Single company')
    solo['rows'] = solo['rows'][:1]
    displayed = display_metrics([dict(result=dict(metrics=[solo,shared]))])
    assert [m['id'] for m in displayed] == [shared['id'],'solo']


def test_collection_prefers_performance_report_over_framework(monkeypatch):
    from app.knowledge.analytical import collect_packet
    import app.knowledge.analytical as module
    def search_fixture(session, request):
        return dict(total=2,items=[dict(evidence_id='framework',text='Definitions and formulas. '*30,document_role='supporting_document'),
            dict(evidence_id='annual',text='Actual results for the reporting year. '*20,document_role='primary_report_candidate')])
    monkeypatch.setattr(module,'search',search_fixture)
    monkeypatch.setattr(module,'coverage',lambda *args:dict(reports_indexed=2,reports_with_text_gaps=0))
    answer = collect_packet(None,dict(report_ids=[]), '01900000-0000-4000-8000-000000000003', 850, 'transition')
    assert list(answer['evidence']) == ['annual']


@pytest.mark.parametrize('operation,operands,expected',[('add',['amount','0'],'2'),('subtract',['amount','0'],'2'),('subtract',['0','amount'],'-2')])
def test_literal_zero_preserves_dimension(operation,operands,expected):
    m=metric(rows=[dict(company_id='a',inputs=[dict(id='amount',fact_id='a:hours',normalised_unit='hours')])],
        steps=[dict(id='result',operation=operation,operands=operands)],result_unit='hours')
    result=calculate(m,facts(),{'a':'A'})
    assert not result['excluded'] and result['rows'][0]['value']==expected


def test_declared_response_namespace_resolves_exact_alias_not_other_company_fact():
    proposal=output()
    proposal.findings[0].id='lens:f1'
    proposal.findings[0].fact_ids=['lens:F1','other-company:F1','lens:invented']
    resolved=resolve_fact_aliases(proposal,{'F1':'actual-company:actual-fact'})
    assert resolved.findings[0].fact_ids==['actual-company:actual-fact','other-company:F1','lens:invented']


def test_legacy_truncated_result_reference_is_resolved_without_changing_arithmetic():
    m=metric()
    identifier='people_social_outcomes_metric_1_result'
    m.steps[-1].id=identifier[:30]
    m.result_step_id=identifier
    value=calculate(m,facts(),{'a':'A','b':'B'})
    assert value['rows'][0]['value']=='50.0'
    assert value['result_step_id']==identifier[:30]


def test_punctuation_only_operand_mismatch_is_resolved_without_model_retry():
    m = metric()
    for row in m.rows:
        for item in row.inputs:
            item.id = 'input_' + item.id
    for step in m.steps:
        step.operands = ['input-' + v if v in {'leaders', 'workforce'} else v for v in step.operands]
    answer = calculate(m, facts(), {'a':'A', 'b':'B'})
    assert len(answer['rows']) == 2
    assert answer['steps'][0]['operands'] == ['input_leaders', 'input_workforce']
    assert Decimal(answer['rows'][0]['value']) == 50


def test_result_unit_scale_is_applied_to_currency_per_customer():
    data = facts()
    data['a:leaders'].update(value='EUR 1,713 million', unit='EUR million')
    data['a:workforce'].update(value='180 million', unit='customers')
    m = metric(rows=[dict(company_id='a', inputs=[dict(id='spend',fact_id='a:leaders',normalised_unit='EUR million'),
        dict(id='customers',fact_id='a:workforce',normalised_unit='customers')])],
        steps=[dict(id='result',operation='divide',operands=['spend','customers'])],result_unit='EUR/customer')
    answer = calculate(m, data, {'a':'A'})
    assert not answer['excluded']
    assert abs(Decimal(answer['rows'][0]['value']) - Decimal('9.516666666666667')) < Decimal('1e-12')
    assert answer['rows'][0]['result_conversion_factor'] == '1000000'


def test_mixed_currency_scales_cancel_in_ratio_and_addition():
    data = facts()
    data['a:leaders'].update(value='2',unit='EUR million')
    data['a:workforce'].update(value='500000',unit='EUR')
    m = metric(rows=[dict(company_id='a',inputs=[dict(id='leaders',fact_id='a:leaders',normalised_unit='EUR million'),
        dict(id='workforce',fact_id='a:workforce',normalised_unit='EUR')])])
    assert Decimal(calculate(m,data,{'a':'A'})['rows'][0]['value']) == 400
    m.steps = [type(m.steps[0])(id='result',operation='add',operands=['leaders','workforce'])]
    m.result_unit = 'EUR'
    row = calculate(m,data,{'a':'A'})['rows'][0]
    assert Decimal(row['value']) == 2500000
    assert row['step_conversions']['result'] == '0.000001'


def test_target_deadline_does_not_become_observation_year():
    data = facts()
    data['a:workforce'].update(kind='target',year=2030)
    answer = calculate(metric(),data,{'a':'A','b':'B'})
    assert answer['rows'][0]['year'] == 2025


def test_unused_denominator_rejects_affected_row_not_other_peers():
    from app.knowledge.analysis_contract import Input
    m=metric()
    m.rows[0].inputs.append(Input(id='unused_total',fact_id='a:hours',normalised_unit='hours'))
    value=calculate(m,facts(),{'a':'A','b':'B'})
    assert [r['company_id'] for r in value['rows']]==['b']
    assert value['excluded']==[{'company_id':'a','reason':'unused_metric_input'}]


def test_average_per_employee_label_preserves_rate_despite_abbreviated_unit():
    data=facts()
    for c in 'ab':
        for field in ('leaders','workforce'):
            data[f'{c}:{field}'].update(unit='hours',metric='Average training hours per employee')
    m=metric()
    for row in m.rows:
        for item in row.inputs:item.normalised_unit='hours per employee'
    value=calculate(m,data,{'a':'A','b':'B'})
    assert len(value['rows'])==2
    assert value['rows'][0]['value']=='50.0'
    assert value['rows'][0]['inputs'][0]['raw_unit']=='hours'


def test_numeric_award_does_not_publish_unused_model_points_rubric():
    proposal = output()
    from app.knowledge.analysis_contract import RubricItem
    proposal.awards[0].rubric = [RubricItem(id='unused',criterion='Unused points',evidence_required='Not used in numeric ranking',max_points=5)]
    ledgers = [dict(company_id=c, facts=[f for f in facts().values() if f['company_id']==c]) for c in 'ab']
    badge = assemble(proposal,ledgers,{'companies':[dict(id=c,company_name=c) for c in 'ab']})['badges'][0]
    assert badge['winner_ids'] == ['a','b']
    assert badge['rubric'] == [] and badge['assessments'] == []


def test_converts_units_and_supports_more_than_two_inputs():
    data=facts()
    for c in ('a','b'):
        data[c+':leaders'].update(value='2',unit='MtCO2e')
        data[c+':workforce'].update(value='500',unit='ktCO2e')
        data[c+':hours'].update(value='1000',unit='million_USD')
    rows=[dict(company_id=c,inputs=[dict(id=n,fact_id=c+':'+n,normalised_unit=u) for n,u in [('leaders','tCO2e'),('workforce','tCO2e'),('hours','million_USD')]]) for c in ('a','b')]
    calculated=calculate(metric(rows=rows,steps=[dict(id='total',operation='add',operands=['leaders','workforce']),dict(id='result',operation='divide',operands=['total','hours'])],result_unit='tCO2e / million USD'),data,{'a':'A','b':'B'})
    assert Decimal(calculated['rows'][0]['value'])==2500
    assert calculated['rows'][0]['inputs'][0]['conversion_factor']=='1000000'


def test_currency_cancels_in_ratios_but_not_absolute_intensity():
    data=facts()
    rows=[]
    for c,currency in [('a','USD'),('b','EUR')]:
        for n in ('leaders','workforce'):data[f'{c}:{n}']['unit']=currency
        rows.append(dict(company_id=c,inputs=[dict(id=n,fact_id=f'{c}:{n}',normalised_unit=currency) for n in ('leaders','workforce')]))
    assert len(calculate(metric(rows=rows),data,{'a':'A','b':'B'})['rows'])==2
    with pytest.raises(ValueError,match='inconsistent_result_units'):
        calculate(metric(rows=rows,steps=[dict(id='result',operation='add',operands=['leaders','workforce'])]),data,{'a':'A','b':'B'})


@pytest.mark.parametrize('broken', ['zero','unknown','forward','unit'])
def test_bad_operand_does_not_destroy_other_company(broken):
    data=facts(); m=metric()
    if broken=='zero':data['a:workforce']['value']='0'
    if broken=='unknown':m.rows[0].inputs[0].fact_id='missing'
    if broken=='forward':m.steps[0].operands[1]='future'
    if broken=='unit':m.rows[0].inputs[0].normalised_unit='GWh'
    response=calculate(m,data,{'a':'A','b':'B'})
    assert response['excluded']
    assert len(response['rows'])==(0 if broken=='forward' else 1)


def test_checklist_deductions_and_incomplete_search_not_zero():
    ledgers=[{'company_id':c,'disclosures':{'scope1':{'status':'disclosed'},'scope3':{'status':state,'reason':'No disclosure in completed search'}}} for c,state in [('a','disclosed'),('b','disclosed'),('c','not_identified'),('d','pending')]]
    scores=disclosure_scores(ledgers,{c:c for c in 'abcd'})
    assert [r['score'] for r in scores['rows']]==[100,100,50,None]
    assert scores['rows'][2]['deductions'][0]['points']==50


def test_whole_report_scorecard_and_promises_include_every_collection_lens():
    sections = []
    for company in ('a', 'b'):
        for criterion in ('workforce', 'scope1'):
            identifier = f'{company}:{criterion}'
            source = {**sources()['S1'], 'evidence_id': identifier, 'company_id': company}
            sections.append(dict(kind='collect', result=dict(company_id=company,
                facts=[dict(id=identifier, source=source)],
                disclosures={criterion:dict(status='disclosed', fact_ids=[identifier])},
                promises=[dict(commitment=f'{criterion} commitment', deadline='2030', assessment='Reported ambition', fact_ids=[identifier])]
            )))
    companies = [dict(id=c, company_name=c) for c in ('a', 'b')]
    summary = collection_summary(sections, companies)
    assert len(summary['promises']) == 4
    assert {c['id'] for c in summary['disclosure_scores']['criteria']} == {'workforce', 'scope1'}
    assert all(r['score'] == 100 for r in summary['disclosure_scores']['rows'])
    for row in summary['disclosure_scores']['rows']:
        assert {s['company_id'] for s in row['sources']} == {row['company_id']}
    rendered = document(dict(title='Fixture', definition=dict(companies=companies,package='sector'), sections=sections))
    assert len(rendered['promises']) == 4
    assert len(rendered['disclosure_scores']['criteria']) == 2


def test_fact_grounding_and_unsearched_absence():
    packet={'company_id':'a','evidence':{'s':{**sources()['S1'],'text':'Workforce: 60% women.'}},'searches':{'workforce':{'complete':False}},'coverage':{}}
    evidence=CompanyEvidence(facts=[dict(id='f',metric='Women',value='60',unit='%',year=2025,population='employees',kind='actual',source_id='s',excerpt='60% women.')],promises=[],disclosures=[dict(criterion_id='workforce',status='not_identified',fact_ids=[],reason='Search result')],research_requests=[])
    ledger=grounded_ledger(evidence,packet)
    assert len(ledger['facts'])==1 and ledger['disclosures']['workforce']['status']=='pending'
    evidence.facts[0].value='99'
    assert not grounded_ledger(evidence,packet)['facts']


def test_unknown_finding_numbers_and_duplicate_ids_rejected():
    o=output();o.findings[0].explanation='Both peers have a calculated parity index of 99.'
    ledgers=[dict(company_id='a',facts=list(facts().values()))]
    response=assemble(o,ledgers,{'companies':[dict(id=c,company_name=c) for c in 'ab']})
    assert not response['analytical_findings']
    o.findings[0].id='representation'
    with pytest.raises(ResearchError,match='duplicate_record'):assemble(o,ledgers,{'companies':[]})


def test_no_ten_finding_cap_chapters_and_exports():
    data=result()
    data['analytical_findings']=[{**deepcopy(data['analytical_findings'][0]),'id':f'f{i}','headline':f'Finding {i}','explanation':f'Distinct finding {i}.'} for i in range(23)]
    stages=chapter_stages(data)
    assert set(f'f{i}' for i in range(23)) <= {f for s in stages for f in s['outline']['finding_ids']}
    assert all(sum(len(s['outline'][k]) for k in ('finding_ids','metric_ids','award_ids'))<=4 for s in stages)
    payload={'title':'Fixture','definition':{'package':'company'},'sections':[{'id':'analyse','kind':'analyse','title':'Analysis','result':data}]}
    doc=document(payload)
    assert doc['findings_count']==23 and doc['awards'][0]['operation']=='formula'
    assert doc['badges'][0]['winner_ids']==['a','b']


def test_master_prompt_shared_across_stages():
    text=master('TEST TASK')
    assert 'Cross topic boundaries' in text and 'leadership female share / workforce female share' in text
    assert text.endswith('TEST TASK') and 'OUTPUT CONTRACT FOR THIS PROMPT TRIAL' not in text


def test_production_analysis_authors_final_prose_without_a_later_paid_writer():
    prompt = master('ANALYSE: final client explanation')
    assert 'There is NO later AI writing call' in prompt
    assert '- PUBLISH: receive the saved analysis' not in prompt
    assert '- PUBLISH: receive the saved analysis' in master('COLLECT: unchanged extraction cache')


def test_disclosure_review_can_use_already_grounded_facts_from_other_batches():
    data = facts()
    packet = dict(company_id='a', evidence={}, searches={'training':dict(complete=True)}, coverage={})
    response = CompanyEvidence(facts=[], promises=[], research_requests=[], disclosures=[dict(
        criterion_id='training', status='disclosed', fact_ids=['a:hours'], reason='Training amount for employees')])
    reviewed = grounded_ledger(response, packet, list(data.values()))
    assert reviewed['disclosures']['training']['status'] == 'disclosed'
    response.disclosures[0].fact_ids = ['b:hours']
    assert grounded_ledger(response, packet, list(data.values()))['disclosures']['training']['status'] == 'pending'
    sections = [dict(kind='collect',result=dict(company_id='a',facts=list(data.values()), disclosures={}, promises=[])),
                dict(kind='check',result=reviewed)]
    assert merge_ledgers(sections)[0]['disclosures']['training']['status'] == 'disclosed'


def test_collection_batches_cover_every_passage_and_omit_parser_metadata():
    evidence = {f's{i}': {'text': 'source evidence ' * 100, 'headings': ['parser noise'] * 1000,
                          'report': 'Fixture', 'page': i + 1} for i in range(7)}
    packet = dict(evidence=evidence, searches={'scope1': dict(complete=True, supplied_ids=list(evidence))})
    batches = collection_batches(packet, limit=3200)
    assert len(batches) == 4
    assert [s for b in batches for s in b['evidence']] == list(evidence)
    assert all(not b['searches']['scope1']['complete'] for b in batches)
    assert all('headings' not in v for v in model_evidence(batches[0])['evidence'].values())
    assert 'headings' in batches[0]['evidence']['s0']  # Full local source is preserved.


def test_later_passage_batch_does_not_erase_an_identified_disclosure():
    sections = [dict(kind='collect', result=dict(company_id='a', facts=[], promises=[], disclosures={
        'scope1': dict(status=status, fact_ids=['f1'] if status=='disclosed' else [])}))
        for status in ('disclosed', 'pending', 'not_identified')]
    assert merge_ledgers(sections)[0]['disclosures']['scope1']['status'] == 'disclosed'


def test_publication_keeps_unused_collected_facts_without_duplicating_identical_rows():
    f=list(facts().values())[0]
    sections=[dict(id=f'collect:{i}',kind='collect',result={'facts':[f]}) for i in range(2)]
    published=document(dict(title='Evidence',definition={'package':'sector'},sections=sections))
    assert published['reported_facts']==[f]


def test_analytical_continuations_keep_all_metrics_and_badges_in_exports():
    first, second = result(), deepcopy(result())
    second['metrics'][0]['name'] = 'Second distinct relationship'
    second['metrics'][0]['rows'][0]['value'] = '75'
    second['badges'][0]['id'] = 'badge2'
    second['badges'][0]['name'] = 'Second distinction'
    payload=dict(title='Fixture',definition=dict(package='sector'),sections=[
        dict(id=f'analyse:{i}',kind='analyse',title='Analysis',result=data) for i,data in enumerate([first,second])])
    exported=document(payload)
    assert len(exported['badges'])==2 and len(exported['awards'])==2
    assert chapter_stages(first,'analyse:0')[0]['id'] != chapter_stages(second,'analyse:1')[0]['id']


def test_repeated_calculation_has_one_presentation_but_preserves_raw_analysis():
    first, second = result(), deepcopy(result())
    second['metrics'][0].update(id='another_id', name='Same calculation, another title')
    payload = dict(title='Fixture',definition=dict(package='sector'),sections=[
        dict(id=f'analyse:{i}',kind='analyse',title='Analysis',result=data) for i,data in enumerate([first,second])])
    exported = document(payload)
    assert len(exported['awards']) == 1
    assert exported['awards'][0]['equivalent_ids'] == ['representation','another_id']
    assert payload['sections'][1]['result']['metrics'][0]['name'] == 'Same calculation, another title'


def test_publishing_saved_ai_analysis_never_calls_a_provider():
    import asyncio
    from app.knowledge.analytical import execute
    from app.core.config import Settings
    data = result()
    section = chapter_stages(data, 'analyse')[0]
    sections = [dict(id='analyse', result=data)]
    # No database or provider: publication must depend only on saved analysis.
    saved = asyncio.run(execute(None, {}, section, sections, Settings(), None))
    assert saved['claims'] and saved['paragraphs'][0]['citations']
    assert saved['publication_method'] == 'assembled_from_saved_ai_analysis'
    assert saved['estimated_cost_usd'] == '0'


def test_published_award_keeps_one_rubric_and_never_awards_zero_evidence():
    from app.knowledge.publication import display_badges
    a = result()['badges'][0]
    a.update(basis='qualitative')
    zero = {**a, 'name': 'No support', 'rows': [{**r,'value':'0'} for r in a['rows']]}
    alternate = {**a, 'id': 'alternate', 'winner_ids': ['b']}
    timing = {**a, 'name': 'Earliest delivery'}
    displayed = display_badges([dict(result=dict(badges=[a, zero, alternate, timing]))])
    assert displayed == [a]


def test_award_review_rejects_wrong_meaning_without_changing_calculation():
    from app.knowledge.analysis_contract import AwardReview
    from app.knowledge.analytical import apply_award_review
    from app.knowledge.publication import display_badges
    data = result()
    review = AwardReview(checks=[dict(award_id='a1',outcome='rejected',name=None,reason='Metric does not support the claimed distinction.')])
    reviewed = apply_award_review(data,review)
    assert reviewed['metrics'] == data['metrics']
    assert reviewed['badges'][0]['rows'] == data['badges'][0]['rows']
    assert reviewed['badges'][0]['status'] == 'rejected'
    assert display_badges([dict(result=reviewed)]) == []
    assert data['badges'][0]['winner_ids'] == ['a','b']


def test_award_review_requires_complete_checks_and_cannot_change_winners():
    from app.knowledge.analysis_contract import AwardReview
    from app.knowledge.analytical import apply_award_review
    data = result()
    with pytest.raises(ResearchError,match='award_review_incomplete'):
        apply_award_review(data,AwardReview(checks=[]))
    review = AwardReview(checks=[dict(award_id='a1',outcome='clarified',name='Leadership representation in reported employee populations',reason='Specify the population.')])
    reviewed = apply_award_review(data,review)
    assert reviewed['badges'][0]['winner_ids'] == data['badges'][0]['winner_ids']
    assert reviewed['badges'][0]['original_name'] == data['badges'][0]['name']
    review.checks[0].name = None
    with pytest.raises(ResearchError,match='award_review_invalid_name'):
        apply_award_review(data,review)


def test_short_model_references_resolve_to_saved_fact_ids():
    packet = {'company_evidence': [dict(facts=[dict(id='a:leaders',value='30')],
        promises=[dict(fact_ids=['a:leaders'])])], 'previous_records': []}
    supplied, aliases = fact_aliases(packet)
    assert supplied['company_evidence'][0]['promises'][0]['fact_ids']==['F1']
    proposal=output()
    proposal.derived_metrics[0].rows[0].inputs[0].fact_id='F1'
    assert resolve_fact_aliases(proposal,aliases).derived_metrics[0].rows[0].inputs[0].fact_id=='a:leaders'
    source=dict(evidence_id='s1',quote='Reported 30%',text='a'*10000,headings=['noise']*1000,page=12)
    compact=compact_sources(dict(inputs=[dict(source=source)]))
    assert compact['inputs'][0]['source']['quote']=='Reported 30%'
    assert 'text' not in compact['inputs'][0]['source']


def test_selected_topics_plan_relevant_lenses_for_every_company():
    companies=[dict(id=c,company_name=c) for c in 'abc']
    planned=stages(companies,['emissions','targets'])
    assert len(planned)==7
    assert all(s.get('lens')=='transition' for s in planned if s['kind'] != 'check')
    assert [s['kind'] for s in planned] == ['collect']*3 + ['check']*3 + ['analyse']
    assert len(stages(companies,['emissions','people','innovation']))==15


def test_ratio_cannot_reuse_one_fact_as_two_distinct_populations():
    proposed=metric()
    proposed.rows[0].inputs[1].fact_id=proposed.rows[0].inputs[0].fact_id
    answer=calculate(proposed,facts(),{'a':'A','b':'B'})
    assert len(answer['rows'])==1
    assert answer['excluded'][0]['reason']=='same_fact_used_as_distinct_inputs'


def test_qualitative_award_uses_same_rubric_and_cited_assessments():
    proposal=output()
    proposal.awards[0]=type(proposal.awards[0])(
        id='observable',name='Execution clarity',why_it_matters='Recognises described implementation.',basis='qualitative',metric_id=None,
        rubric=[dict(id='programme',criterion='Evidence of implemented programme',evidence_required='Cited activity and outcome',max_points=2)],
        assessments=[dict(company_id=c,criterion_id='programme',points=points,fact_ids=[f'{c}:hours'],explanation='Fixture assessment') for c,points in [('a',2),('b',1)]])
    names={'companies':[dict(id=c,company_name=c) for c in 'ab']}
    ledgers=[dict(company_id=c,facts=[f for f in facts().values() if f['company_id']==c]) for c in 'ab']
    badge=assemble(proposal,ledgers,names)['badges'][0]
    assert badge['winner_ids']==['a'] and badge['rows'][0]['sources']
    proposal.awards[0].assessments[0].points=3
    badge=assemble(proposal,ledgers,names)['badges'][0]
    assert badge['status']=='pending'  # Out-of-rubric points cannot produce a winner.


def test_percentage_suffixes_and_explicit_common_benchmark_are_usable():
    data=facts()
    data['a:leaders']['value']='30%'
    data['a:leaders']['unit']='% lower'
    data['b:workforce'].update(kind='contextual',population='Sectoral benchmark',value='60')
    m=metric()
    m.rows[0].inputs[1].fact_id='b:workforce'
    calculated=calculate(m,data,{'a':'A','b':'B'})
    assert calculated['rows'][0]['value']=='50.0'
    assert calculated['rows'][0]['inputs'][0]['raw_numeric_value']=='30'
    assert calculated['rows'][0]['inputs'][0]['raw_value']=='30%'
    data['b:workforce']['kind']='actual'
    assert calculate(m,data,{'a':'A','b':'B'})['excluded'][0]['reason']=='invalid_metric_fact'
