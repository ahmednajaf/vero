"""Unit conversion shared by extraction, comparison and published editions.

Scale is not comparability: convert compatible dimensions automatically, then let
the caller describe metric boundaries. Currency conversion needs an explicit FX
rate; power is not energy and CO2 is not CO2-equivalent.
"""
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, localcontext


@dataclass(frozen=True)
class Unit:
    symbol: str
    dimension: str
    factor: Decimal


UNITS: dict[str, Unit] = {}


def key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().strip('()[]').strip().rstrip('.')
    value = re.sub(r'CO2[\s-]*(?:equivalents?|eq\.?)(?!\w)', 'CO2e', value, flags=re.I)
    value = value.replace("CO2-eq", "CO2e").replace("CO2eq", "CO2e").replace("CO2-e", "CO2e")
    value = re.sub(r"\b(?:of )?carbon dioxide equivalent\b", "CO2e", value, flags=re.I)
    value = re.sub(r"\bco2(?: equivalent| equivalents)\b", "CO2e", value, flags=re.I)
    return re.sub(r"\s+", " ", value)


def register(symbol: str, dimension: str, factor: str, *aliases: str) -> None:
    unit = Unit(symbol, dimension, Decimal(factor))
    for name in (symbol, *aliases):
        UNITS[key(name)] = unit


for symbol, factor, names in (
    ("kg", "0.001", ("kilogram", "kilograms")),
    ("t", "1", ("tonne", "tonnes", "metric ton", "metric tons", "metric tonne", "metric tonnes")),
    ("kt", "1000", ("kilotonnes", "kilotons", "thousand tonnes", "thousand metric tons", "1,000 tonnes")),
    ("Mt", "1000000", ("million tonnes", "million metric tons", "million metric tonnes")),
):
    register(symbol, "mass", factor, *names)
    register(symbol+"CO2e", "ghg", factor, symbol+" CO2e", *[n+" CO2e" for n in names], *[n+" of CO2e" for n in names])
register("MtCO2e", "ghg", "1000000", "MMtCO2e", "MMtCO2 e", "MMt CO2e", "million tCO2e", "million t CO2e")
register("ktCO2e", "ghg", "1000", "GgCO2e")
register("ktCO2e", "ghg", "1000", "000 tonnes CO2e", "'000 tonnes CO2e", "‘000 tonnes CO2e", "’000 tonnes CO2e")
for symbol, factor, energy_aliases in (
    ("MWh", "1", ("megawatt hours", "megawatt-hours")),
    ("kWh", "0.001", ("kilowatt hours", "kilowatt-hours")),
    ("GWh", "1000", ("gigawatt hours", "gigawatt-hours")),
    ("TWh", "1000000", ("terawatt hours", "terawatt-hours")),
    ("GJ", "1", ("gigajoules",)),
    ("MJ", "0.001", ("megajoules",)),
    ("TJ", "1000", ("terajoules",)),
    ("PJ", "1000000", ("petajoules",)),
    ("MMBtu", "1.05505585262", ("million Btu",)),
    ("kBtu", "0.00105505585262", ("thousand Btu", "thousands Btu")),
):
    # Store energy internally as GJ, avoiding a repeating decimal until division.
    scale = Decimal(factor) * (Decimal("3.6") if symbol.endswith("Wh") else 1)
    register(symbol, "energy", str(scale), *energy_aliases)
for symbol, factor, aliases in (
    ("m3", "1", ("m³", "cubic metres", "cubic meters")),
    ("L", "0.001", ("litres", "liters", "l")),
    ("ML", "1000", ("megalitres", "megaliters", "million litres", "million liters")),
    ("million_m3", "1000000", ("million m3", "million m³", "million cubic metres", "million cubic meters", "Mm3")),
    ("thousand_m3", "1000", ("thousand m3", "thousand cubic metres")),
    ("bbl", "0.158987294928", ("barrels",)),
):
    register(symbol, "volume", factor, *aliases)
register("%", "percentage", "1", "percent", "percentage", "per cent", "% reduction", "% lower", "% decrease", "% increase", "% change")
register("fraction", "percentage", "100", "ratio")
register("persons", "people", "1", "people", "person", "employees", "employee", "individuals", "headcount", "colleagues", "colleague")
register("FTE", "full_time_equivalents", "1", "FTEs", "full-time equivalent", "full-time equivalents")
register("customers", "customers", "1", "customer")
register("hours", "time", "1", "hour", "h", "hr")
register("million_hours", "time", "1000000", "million hours")
register("count", "count", "1", "number")
register("$", "currency_dollar_symbol", "1", "dollars")
register("million_$", "currency_dollar_symbol", "1000000", "$ million", "million dollars", "$m", "$ m")
register("billion_$", "currency_dollar_symbol", "1000000000", "$ billion", "billion dollars", "$bn", "$ bn")
register("trillion_$", "currency_dollar_symbol", "1000000000000", "$ trillion", "trillion dollars", "$tn", "$trn")
register("boe", "oil_equivalent", "1", "barrel of oil equivalent", "barrels of oil equivalent")
register("million_boe", "oil_equivalent", "1000000", "million boe", "MMboe")
for currency in ("USD", "EUR", "GBP", "SAR", "NOK"):
    register(currency, "currency_"+currency, "1")
    register("million_"+currency, "currency_"+currency, "1000000", "million "+currency, currency+" million", currency+"m", currency+" m")
    register("billion_"+currency, "currency_"+currency, "1000000000", "billion "+currency, currency+" billion", currency+"bn", currency+" bn")
    register("trillion_"+currency, "currency_"+currency, "1000000000000", "trillion "+currency, currency+" trillion", currency+"tn", currency+" trn")
for symbol, currency in (('€','EUR'),('£','GBP'),('US$','USD')):
    register(currency, 'currency_'+currency, '1', symbol)
    register('million_'+currency, 'currency_'+currency, '1000000', symbol+' million', 'million '+symbol, symbol+'m', symbol+' m')
    register('billion_'+currency, 'currency_'+currency, '1000000000', symbol+' billion', 'billion '+symbol, symbol+'bn', symbol+' bn')


def parse_unit(raw: str) -> Unit | None:
    cleaned = key(raw)
    direct = UNITS.get(cleaned) or UNITS.get(cleaned.replace(" ", ""))
    if direct:
        return direct
    # Percentage qualifiers change the measure's meaning, not its unit scale.
    # Definitions/populations remain on the fact and calculation, separately.
    if re.match(r'^(?:%|percent)\s+(?:of|reduction|lower|decrease|increase|change|absolute|interest)\b', cleaned, re.I):
        return UNITS['%']
    # Word aliases are case-insensitive; SI symbols retain meaningful case.
    if len(cleaned) > 10:
        direct = next((u for alias, u in UNITS.items() if " " in alias and alias.casefold() == cleaned.casefold()), None)
        if direct:
            return direct
    parts = re.split(r"\s+per\s+|/", cleaned, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        numerator, denominator = parse_unit(parts[0]), parse_unit(parts[1])
        if numerator and denominator:
            with localcontext() as context:
                context.prec = 50
                return Unit(f"{numerator.symbol}/{denominator.symbol}", f"{numerator.dimension}/{denominator.dimension}", numerator.factor / denominator.factor)
    return None


def convert(value: Decimal, source: str, target: str) -> Decimal | None:
    origin, destination = parse_unit(source), parse_unit(target)
    if not value.is_finite() or origin is None or destination is None or origin.dimension != destination.dimension:
        return None
    with localcontext() as context:
        context.prec = 50
        return value * origin.factor / destination.factor


def quantity(raw: str, unit: str | None) -> Decimal | None:
    """A single reported amount, including a scale word in the value column.

    No ranges, bundled table cells, inequality estimates or guessed denominators.
    Preserve the original string separately; avoid double-scaling 'million USD'.
    """
    value = unicodedata.normalize('NFKC', raw).strip().replace(',', '').removesuffix('Δ').strip()
    # Keep the raw label, but recognise a scalar explicitly described as a
    # percentage change. Do not turn prose, ranges or inequalities into amounts.
    value = re.sub(r'(?<=%)\s+(?:reduction|decrease|increase|growth)$', '', value, flags=re.I)
    matched = re.fullmatch(r'(?:US\$|USD\s*|EUR\s*|GBP\s*|[$€£])?\s*(-?\d+(?:\.\d+)?)\s*(thousand|million|billion|trillion|bn|tn|trn|m)?\s*%?', value, re.I)
    if not matched:
        return None
    amount = Decimal(matched[1])
    if matched[2]:
        label = {'bn':'billion', 'tn':'trillion', 'trn':'trillion', 'm':'million'}.get(matched[2].lower(), matched[2].lower())
        scale = {'thousand': Decimal(1000), 'million': Decimal(1000000), 'billion': Decimal(1000000000), 'trillion': Decimal(1000000000000)}[label]
        parsed = parse_unit(unit or '')
        scaled_unit = parsed and parsed.factor == scale
        if parsed and parsed.dimension.startswith('currency_'):
            amount *= scale / parsed.factor
        elif not scaled_unit and not re.search(r'\b' + label + r'\b', (unit or '').replace('_', ' '), re.I):
            amount *= scale
    return amount
