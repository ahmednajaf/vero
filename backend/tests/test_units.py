from decimal import Decimal as D
import pytest


@pytest.mark.parametrize('raw,unit,expected', [('16.6 million','hours','16600000'),('$541 million','USD','541000000'),('1.5 billion','billion USD','1.5'),('30%','%','30'),('Male 2; Female 3','persons',None),('2–4','hours',None)])
def test_reported_quantity_scale(raw, unit, expected):
    from app.extraction.units import quantity
    from decimal import Decimal
    assert quantity(raw, unit) == (Decimal(expected) if expected is not None else None)
from app.extraction.units import convert
from app.extraction.normalisation import normalise
from app.catalogue.seed import load_catalogue


@pytest.mark.parametrize('source,target,expected',[
    ('MtCO2eq.','tCO2e','1000000'),
    ('million tonnes CO2-equivalent','tCO2e','1000000'),
    ('(€ million)','EUR','1000000'),
    ('£ billion','GBP','1000000000'),
])
def test_report_unit_punctuation_and_unambiguous_currency_symbols(source,target,expected):
    assert convert(D(1),source,target)==D(expected)


@pytest.mark.parametrize("value,source,target,expected", [
    ("1", "million metric tons of CO2e", "tCO2e", "1000000"),
    ("1", "Million metric tonnes CO₂e", "kgCO2e", "1000000000"),
    ("2", "MMtCO2e", "ktCO2e", "2000"),
    ("3600", "GJ", "MWh", "1000"),
    ("1", "TWh", "GJ", "3600000"),
    ("1", "MMBtu", "GJ", "1.05505585262"),
    ("2", "million m³", "ML", "2000"),
    ("5000", "litres", "m3", "5"),
    ("2", "million tonnes", "t", "2000000"),
    ("10", "kgCO2e/boe", "tCO2e/boe", "0.01"),
    ("2", "tCO2e/million USD", "kgCO2e/USD", "0.002"),
    ("0.35", "fraction", "%", "35"),
    ("2", "billion USD", "million USD", "2000"),
    ("2", "$ billion", "$ million", "2000"),
    ("35", "percent increase", "%", "35"),
    ("45", "% absolute reduction", "%", "45"),
    ("3", "hours per employee", "hours/persons", "3"),
])
def test_dimensionally_correct_conversions(value, source, target, expected):
    assert convert(D(value), source, target) == D(expected)


@pytest.mark.parametrize("source,target", [("MW","MWh"),("kgCO2e","kg"),("tCO2","tCO2e"),("EUR","USD"),("tCO2e/boe","tCO2e/USD"),("mtCO2e","tCO2e"),("$ million","million USD"),("days","hours")])
def test_distinct_quantities_are_not_unit_conversions(source,target):
    assert convert(D(1),source,target) is None


def test_canonical_conversion_preserves_source_and_accepts_repeating_decimal():
    metrics={m.canonical_id:m for m in load_catalogue().metrics}
    unit="Million metric tonnes CO₂e"
    assert normalise(metrics["scope_1_emissions"],"58",unit).value == D("58000000")
    assert unit == "Million metric tonnes CO₂e"
    assert normalise(metrics["total_energy_consumption"],"1","TWh").value == D("3600000")
@pytest.mark.parametrize('origin,target', [('$bn', '$ bn'), ('€ bn','EUR billion'), ('$m', 'million_$')])
def test_compact_currency_abbreviations(origin, target):
    assert convert(D('1'),origin,target) == 1


@pytest.mark.parametrize('raw,unit,expected', [('$98.5bn','USD bn','98.5'),('£274m','GBP m','274'),('$1.8tn','USD','1800000000000'),('97%Δ','%','97'),('84.9% reduction','%','84.9')])
def test_financial_scale_suffixes_and_assurance_marker(raw, unit, expected):
    from app.extraction.units import quantity
    assert quantity(raw,unit) == D(expected)


def test_thousands_in_table_unit_header():
    assert convert(D('5.2'), '000 tonnes CO2e', 'tCO2e') == 5200


def test_currency_value_scale_is_expressed_in_its_unit_not_double_scaled():
    from app.extraction.units import quantity
    assert quantity('$1trn', 'USD bn') == 1000
    assert quantity('2bn', 'EUR million') == 2000
    assert convert(D('1'), 'trillion USD', 'billion USD') == 1000
    assert convert(D('98141'), 'colleagues', 'employees') == 98141
