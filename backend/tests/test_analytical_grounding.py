"""Typography and year-column regressions; no HTTP or model calls."""
import json
from decimal import Decimal

import pytest

from app.extraction.units import convert
from app.knowledge.grounding import canonical, resolve_excerpt
from app.knowledge.analytical import grounded_ledger
from app.knowledge.analysis_contract import CompanyEvidence


def ledger(text, excerpt, value='58', unit='MtCO2e', year=2025):
    evidence = CompanyEvidence(facts=[dict(id='f',metric='Emissions',value=value,unit=unit,year=year,
        population='Reported operations',kind='actual',source_id='s',excerpt=excerpt)],
        promises=[],disclosures=[],research_requests=[])
    return grounded_ledger(evidence,dict(company_id='c',evidence={'s':dict(text=text,page=13)},searches={},coverage={}))


@pytest.mark.parametrize(('text','excerpt','value'), [
    ('58.0\n\x07Scope 1 emissions\n(million metric tons\nof CO2e)', '58.0 Scope 1 emissions (million metric tons of CO2e)', '58'),
    ('14.0\nScope 2 market-\nbased emissions', '14.0 Scope 2 market-based emissions','14'),
    ('10.0\nUpstream carbon\nintensity (kg CO2e/\nboe)', '10.0 Upstream carbon intensity (kg CO2e/boe)','10'),
    ('Scope 1+2\n Mt CO2e\n33\n34\n35\n46', r'Scope 1+2 \n Mt CO2e \n33 \n34 \n35 \n46','33'),
    ('Methane emissions decreased by –65%.','Methane emissions decreased by -65%.','-65'),
])
def test_preserves_original_source_despite_pdf_typography(text,excerpt,value):
    fact = ledger(text,excerpt,value)['facts'][0]
    assert fact['source']['quote'] in text
    assert fact['source']['model_excerpt']==excerpt
    assert fact['source']['grounding_method']=='normalized_literal'


def test_decode_table_cell_json_without_altering_stored_source():
    text=json.dumps(['Methane-\nemission intensity was 0.08%.',None,'Other column'])
    fact=ledger(text,'Methane-emission intensity was 0.08%.','0.08','%')['facts'][0]
    assert fact['source']['text']==text
    assert fact['source']['quote']=='Methane-\nemission intensity was 0.08%.'


def test_qualitative_multicolumn_quote_can_change_line_order_not_words():
    first = 'The company reports all fifteen Scope 3 categories in its reporting.'
    second = 'Categories include purchased goods and services and use of sold products.'
    text = first + '\n' + second
    found = resolve_excerpt(text, second + '\n' + first, 'Categories are reported', None, 2025)
    assert found and found.method == 'literal_reordered_lines' and found.quote == text
    assert resolve_excerpt(text, second + '\n' + first.replace('fifteen','fourteen'), 'Categories', None, 2025) is None
    assert resolve_excerpt(text, second + '\n' + first, '15', 'count', 2025) is None


TABLE = '''GHG emissions
Unit
2025
2024
% Change
Scope 1 GHG emissions1
million tCO2e
7.8
8.3
 -5 %
Scope 2 GHG emissions (location-based)1
million tCO2e
0.08
0.08
 -1 %
Scope 2 GHG emissions (market-based)1
million tCO2e
1.2
1.5
 -19 %'''


def test_year_header_and_row_are_grounded_together():
    excerpt='Scope 1 GHG emissions ... 2025 7.8 2024 8.3 -5 %'
    fact=ledger(TABLE,excerpt,'7.8','million tCO2e')['facts'][0]
    assert fact['source']['grounding_method']=='year_labelled_table'
    assert '2025\n2024' in fact['source']['quote']
    assert 'Scope 1 GHG emissions1' in fact['source']['quote']
    assert 'Scope 2' not in fact['source']['quote']
    assert convert(Decimal('7.8'),'million tCO2e','tCO2e')==7800000


@pytest.mark.parametrize(('excerpt','value','unit','year'), [
    ('Scope 1 GHG emissions ... 2025 8.3','8.3','million tCO2e',2025),
    ('Scope 2 GHG emissions (market-based) ... 2025 7.8','7.8','million tCO2e',2025),
    ('Scope 1 GHG emissions ... 2025 7.8','7.8','GWh',2025),
    ('Scope 1 GHG emissions ... 2023 7.8','7.8','million tCO2e',2023),
])
def test_rejects_neighbouring_row_year_or_wrong_units(excerpt,value,unit,year):
    assert not ledger(TABLE,excerpt,value,unit,year)['facts']


def test_ambiguous_boundary_rows_are_not_arbitrarily_selected():
    text=TABLE+'\nOperational control\nScope 1 GHG emissions1\nmillion tCO2e\n7.8\n8.3'
    assert not ledger(text,'Scope 1 GHG emissions ... 2025 7.8','7.8','million tCO2e')['facts']


def test_ellipsis_preserves_omitted_qualifier():
    text='Emissions declined 10%, mainly because assets were sold. Operational improvements contributed less.'
    quote='Emissions declined 10% ... Operational improvements contributed less.'
    fact=ledger(text,quote,'10','%')['facts'][0]
    assert 'assets were sold' in fact['source']['quote']
    assert fact['source']['quote'] in text
    assert not ledger(text,'Emissions declined 10% ... Our operations achieved all of this.','10','%')['facts']


@pytest.mark.parametrize(('text','quote','value'), [
    ('Carbon credits [C]\n —','Carbon credits [C] —','0'),
    ('Scope 1\n58','Scope 1','58'),
    ('Emissions 58, another measure 99','Emissions 58','99'),
    ('Value NaN','Value NaN','NaN'),
])
def test_no_missing_to_zero_or_unquoted_number_recovery(text,quote,value):
    assert not ledger(text,quote,value)['facts']


def test_source_typography_does_not_change_numerical_signs():
    assert '-65%' in canonical('–65%')
    assert 'scope 1' != canonical('Scope 2')
    assert resolve_excerpt('A 33% reduction.','A 34% reduction.','34','%',2025) is None


def test_reordered_kpi_card_requires_adjacent_value_and_reported_year():
    text='2025 progress\n14.0\nScope 2 market-\nbased emissions\n(million metric tons of CO2e)\n58.0\nScope 1 emissions\n(million metric tons of CO2e)'
    result=resolve_excerpt(text,'Scope 1 emissions (million metric tons of CO2e) 58','58','MtCO2e',2025)
    assert result and result.method=='adjacent_kpi_card' and result.quote in text
    assert resolve_excerpt(text,'Scope 1 emissions (million metric tons of CO2e) 14','14','MtCO2e',2025) is None
    assert resolve_excerpt(text,'Scope 1 emissions (million metric tons of CO2e) 58','58','MtCO2e',2024) is None


def test_citation_quotation_marks_are_not_part_of_the_report():
    result=resolve_excerpt('Methane intensity was 0.08%.','“Methane intensity was 0.08%.”','0.08','%',2025)
    assert result and result.quote=='Methane intensity was 0.08%.'
