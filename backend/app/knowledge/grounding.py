"""Resolve model citations to original text or explicit year-labelled table cells.

This repairs presentation differences, not facts. It does not fuzzy-match words,
accept numbers merely occurring somewhere on a page, or infer missing cells.
"""
import json
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.extraction.units import convert


@dataclass(frozen=True)
class GroundedExcerpt:
    quote: str
    method: str
    row_years: tuple[int, ...] = ()


def readable_text(text: str) -> str:
    """Tables are stored as JSON cell arrays; decode their actual textual content."""
    if text.lstrip().startswith('['):
        try:
            cells = json.loads(text)
            if isinstance(cells, list):
                return '\n'.join(str(v) for v in cells if isinstance(v, (str, int, float)))
        except (ValueError, TypeError):
            pass
    return text


def canonical(text: str) -> str:
    text = unicodedata.normalize('NFKC', text).replace('\u00ad', '')
    text = text.replace('\\n', ' ').replace('\\t', ' ')
    typography: dict[str, str | int | None] = {'−':'-', '‐':'-', '‑':'-', '–':'-', '—':'-', '’':"'", '‘':"'", '“':'"', '”':'"'}
    text = text.translate(str.maketrans(typography))
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    # Discretionary and ordinary word hyphens are typography, not numerical signs.
    text = re.sub(r'(?<=[a-zA-Z])-\s*(?=[a-zA-Z])', '', text)
    text = re.sub(r'\s*([/()])\s*', r'\1', text)
    return re.sub(r'\s+', ' ', text).strip().casefold()


def _original_span(text: str, start: int, end: int) -> str:
    """Map a normalized match back to a verbatim source slice.

    Passage sizes are small. Prefix lengths keep Unicode expansions, soft hyphens
    and PDF whitespace mapped without altering the stored source.
    """
    # Match on whole lines first; normalization across line breaks remains valid.
    lines = text.splitlines(keepends=True)
    positions, offset = [], 0
    for line in lines:
        positions.append((offset, len(canonical(text[:offset]))))
        offset += len(line)
    first = max((i for i, p in enumerate(positions) if p[1] <= start), default=0)
    last = next((i for i, p in enumerate(positions) if p[1] >= end), len(lines))
    return ''.join(lines[first:max(first+1,last)]).strip()


def literal_excerpt(text: str, excerpt: str) -> GroundedExcerpt | None:
    """Literal citation matching tolerant of PDF typography, not changed facts."""
    text = readable_text(text)
    excerpt = excerpt.strip().strip('"“”').strip().strip('…').strip()
    haystack, needle = canonical(text), canonical(excerpt)
    if not needle:
        return None
    start = haystack.find(needle)
    if start >= 0:
        return GroundedExcerpt(_original_span(text,start,start+len(needle)), 'normalized_literal')
    pieces = [canonical(p) for p in re.split(r'\.{3,}|…',excerpt) if canonical(p)]
    if len(pieces)<2 or any(len(p)<8 for p in pieces):
        return None
    start,cursor = -1,0
    for piece in pieces:
        found=haystack.find(piece,cursor)
        if found<0:
            return None
        if start<0:
            start=found
        cursor=found+len(piece)
    if cursor-start>1500:
        return None
    return GroundedExcerpt(_original_span(text,start,cursor),'ordered_source_fragments')


def number(value: str) -> Decimal | None:
    cleaned = canonical(value).replace(',', '').replace(' ', '').removesuffix('%')
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', cleaned):
        return None
    try:
        result = Decimal(cleaned)
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def _label(text: str) -> str:
    # Attached superscript footnotes occur after labels, not as part of scope IDs.
    value = canonical(text)
    value = re.sub(r'(?<!scope)(?<=[a-z)])\d+(?:,\d+)*$', '', value)
    return re.sub(r'\s+', ' ', value).strip()


def table_row(text: str, excerpt: str, value: str, unit: str | None, year: int | None) -> GroundedExcerpt | None:
    """Match a row label AND its requested year/value, never a neighbouring row.

    Supports the common PDF layout: year header, row label, unit, then one value
    per year. Multiple boundary sections are retained. Ambiguous matches fail.
    """
    expected = number(value)
    if expected is None or unit is None or year is None:
        return None
    lines = text.splitlines()
    headers: list[tuple[int, tuple[int, ...]]] = []
    for i, line in enumerate(lines):
        if not re.fullmatch(r'(?:19|20)\d{2}', line.strip()):
            continue
        if i and re.fullmatch(r'(?:19|20)\d{2}', lines[i-1].strip()):
            continue
        header_years = []
        for following in lines[i:i+8]:
            if re.fullmatch(r'(?:19|20)\d{2}', following.strip()):
                header_years.append(int(following))
            else:
                break
        if len(header_years) >= 2 and len(set(header_years)) == len(header_years):
            headers.append((i, tuple(header_years)))
    query = canonical(excerpt)
    matches = []
    for i, line in enumerate(lines):
        applicable = [(j, years) for j, years in headers if j < i]
        if not applicable:
            continue
        header_index, years = applicable[-1]
        if year not in years:
            continue
        # The row's unit must be compatible with the model's raw unit.
        factor = convert(Decimal(1), unit, line.strip())
        if factor is None:
            continue
        values, end = [], i+1
        for j in range(i+1, min(len(lines),i+len(years)+2)):
            if not lines[j].strip():
                continue
            numeric = number(lines[j])
            if numeric is None:
                break
            values.append(numeric)
            end = j+1
        index = years.index(year)
        if len(values) < len(years) or values[index] != expected * factor:
            continue
        # A second explicitly cited year distinguishes identical values reported
        # for different boundaries on the same page.
        cited_years = re.findall(r'\b((?:19|20)\d{2})\s+(-?\d+(?:\.\d+)?)', query)
        if any(int(y) in years and values[years.index(int(y))] != Decimal(v)*factor for y,v in cited_years):
            continue
        # At least one literal descriptive row label must be in the citation.
        # A generic "Scope 1" cannot establish the more specific adjacent metric.
        candidates = [(_label(lines[i-1]), i-1)] if i else []
        if i > 1:
            candidates.append((_label(' '.join(lines[i-2:i])), i-2))
        matched = [(label,start) for label,start in candidates if len(label)>=12 and label in query]
        if not matched:
            continue
        _, start = max(matched, key=lambda item: len(item[0]))
        # Keep original header + selected row as separate explicit source spans.
        header = '\n'.join(lines[header_index:header_index+len(years)])
        row = '\n'.join(lines[start:end])
        matches.append(GroundedExcerpt(header+'\n[…]\n'+row, 'year_labelled_table', years))
    unique = {m.quote:m for m in matches}
    return next(iter(unique.values())) if len(unique)==1 else None


def resolve_excerpt(text: str, excerpt: str, value: str, unit: str | None, year: int | None) -> GroundedExcerpt | None:
    text = readable_text(text)
    # Outer quotation marks/omission markers are citation punctuation, not report
    # content. Interior punctuation and words must still be grounded.
    excerpt = excerpt.strip().strip('"“”').strip().strip('…').strip()
    haystack, needle = canonical(text), canonical(excerpt)
    if not needle:
        return None
    position = haystack.find(needle)
    if position >= 0:
        return GroundedExcerpt(_original_span(text,position,position+len(needle)), 'normalized_literal')
    # Annual-report KPI cards frequently put the value ABOVE the label, while a
    # model quotes label then value. Resolve only an immediately adjacent numeric
    # line, the literal full label/unit, and an explicit nearby reporting year.
    tail = re.search(r'(?<![\w.])(-?\d+(?:\.\d+)?)\s*%?$', needle)
    if tail and number(tail.group(1)) == number(value) and year is not None:
        label = needle[:tail.start()].strip()
        card = haystack.find(label) if len(label) >= 12 else -1
        if card >= 0:
            preceding = haystack[max(0,card-1200):card]
            numeric = re.search(r'(-?\d+(?:\.\d+)?)\s*%?\s*$', preceding)
            years = re.findall(r'\b(?:19|20)\d{2}\b', preceding)
            if numeric and number(numeric.group(1)) == number(value) and years and int(years[-1])==year:
                start = card - len(preceding) + numeric.start()
                return GroundedExcerpt(_original_span(text,start,card+len(label)), 'adjacent_kpi_card')
    row = table_row(text, excerpt, value, unit, year)
    if row:
        return row
    # Multi-column PDFs can put a descriptive paragraph below its table while
    # the model quotes it above. For qualitative statements only, accept whole
    # verbatim lines in a different order, never reorder numeric year columns.
    if number(value) is None and unit is None:
        fragments = [canonical(line) for line in excerpt.splitlines() if canonical(line)]
        if (sum(len(f) >= 40 for f in fragments) >= 2
                and all(f in haystack for f in fragments)):
            starts = [haystack.index(f) for f in fragments if len(f) >= 20]
            ends = [haystack.index(f) + len(f) for f in fragments if len(f) >= 20]
            return GroundedExcerpt(_original_span(text, min(starts), max(ends)), 'literal_reordered_lines')
    # Explicit ellipses can join ordered verbatim fragments. Return the entire
    # intervening source, including caveats the model might have omitted.
    pieces = [canonical(p) for p in re.split(r'\.{3,}|…', excerpt) if canonical(p)]
    if len(pieces)<2 or any(len(p)<8 for p in pieces):
        return None
    start, cursor = -1, 0
    for piece in pieces:
        found = haystack.find(piece,cursor)
        if found < 0:
            return None
        if start<0:
            start=found
        cursor=found+len(piece)
    if cursor-start>1500:
        return None
    return GroundedExcerpt(_original_span(text,start,cursor), 'ordered_source_fragments')
