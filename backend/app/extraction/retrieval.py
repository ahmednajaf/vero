"""Stable lexical ranking. Retrieval absence never proves report-level absence."""

import re
import unicodedata
from collections.abc import Iterable

from app.catalogue.contracts import Metric
from app.extraction.contracts import Passage, Retrieved

SECTION_TERMS = {
    "climate": ("emissions", "greenhouse", "carbon", "environmental performance"),
    "energy": ("energy", "electricity", "environmental performance"),
    "water": ("water", "environmental performance"),
    "waste": ("waste", "circular", "environmental performance"),
    "social": ("workforce", "employees", "social performance", "safety"),
    "governance": ("governance", "board", "assurance"),
    "targets": ("targets", "climate", "commitment"),
    "supply_chain": ("supplier", "supply chain", "sourcing"),
    "disclosure_quality": ("methodology", "boundary", "assurance", "emissions"),
}
STOP = {"of", "and", "the", "total", "reported", "percent", "percentage"}


def words(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"scope\s*([123])", r"scope \1", value)
    # Some PDFs attach superscript Roman footnotes to the emissions label.
    # This affects matching only; quoted source text and offsets stay unchanged.
    value = re.sub(r"\bemissions?([ivx]{1,4})\b", "emissions", value)
    variants = {
        "emissions": "emission",
        "employees": "employee",
        "women": "female",
        "withdrawn": "withdrawal",
        "consumed": "consumption",
    }
    return " ".join(
        variants.get(word, word) for word in re.findall(r"[a-z0-9]+", value)
    )


def retrieve(
    passages: Iterable[Passage],
    metric: Metric,
    year: int,
    *,
    top_k: int = 3,
    max_chars: int = 4200,
) -> list[Retrieved]:
    if not 1 <= top_k <= 6 or not 200 <= max_chars <= 4200:
        raise ValueError("Retrieval bounds exceeded")
    aliases = tuple(dict.fromkeys(words(a) for a in [metric.name, *metric.aliases]))
    result = []
    for passage in passages:
        # Never truncate a chunk silently or join pages to satisfy a prompt limit.
        if not passage.text.strip() or len(passage.text) > max_chars:
            continue
        text = words(passage.text)
        padded = f" {text} "
        matches = tuple(a for a in aliases if f" {a} " in padded)
        tokens = set(text.split())
        coverage = max(
            (
                len(tokens & (set(a.split()) - STOP))
                / max(1, len(set(a.split()) - STOP))
                for a in aliases
            ),
            default=0,
        )
        # A category keyword alone must not retrieve an unrelated measure.
        if not matches and coverage < 0.8:
            continue
        scope = re.match(r"scope_([123])(?:_|$)", metric.canonical_id)
        if scope and not re.search(rf"\bscope {scope[1]}\b", text):
            continue
        near_matches = 0
        sequence = text.split()
        for alias in aliases:
            key_tokens = set(alias.split()) - STOP
            if len(key_tokens) >= 2 and any(
                key_tokens.issubset(sequence[i : i + 12]) for i in range(len(sequence))
            ):
                near_matches += 1
        score = (8 if matches or near_matches else 0) + 4 * coverage
        # One strong early row/section label is better evidence than repeated
        # synonyms in a strategy narrative. Alias redundancy must not dominate.
        early = words(passage.text[:300]).split()
        if any((set(alias.split()) - STOP).issubset(early) for alias in aliases):
            score += 6
        score += 3 * (str(year) in tokens)
        score += 2 * bool(re.search(r"\d[,.]\d|\b\d{3,}\b", passage.text))
        # Data-table structure outranks keyword-dense navigation and strategy prose.
        numeric_lines = sum(
            bool(re.fullmatch(r"\s*[+-]?[\d,.]+\s*", line))
            for line in passage.text.splitlines()
        )
        if numeric_lines >= 6:
            score += 6
        if numeric_lines >= 20:
            score += 4
        if scope and scope[1] in {"1", "2"}:
            # A labelled gross-emissions row outranks a regional column header or
            # finance narrative. Do not reward combined Scope 1+2 / intensity rows.
            labels = [
                line
                for line in passage.text.splitlines()
                if re.search(rf"\bscope\s*{scope[1]}\b", line, re.I)
                and (
                    re.search(r"\bemissions?(?:[ivx]{1,4})?\b", line, re.I)
                    or re.fullmatch(
                        rf"\s*scope\s*{scope[1]}(?:\s*\([^)]*\))?\s*", line, re.I
                    )
                )
            ]
            if any(
                not re.search(
                    r"intensity|reduction|target|scope\s*[12].*scope\s*[12]|scopes?\s*1\s*(?:and|&|\+)\s*2",
                    line,
                    re.I,
                )
                for line in labels
            ):
                score += 12
        section = words((passage.section or "") + " " + passage.text[:150])
        score += min(
            4, sum(2 for term in SECTION_TERMS[metric.category] if term in section)
        )
        emissions_table = numeric_lines >= 6 and bool(
            re.search(r"CO[2₂]e|carbon dioxide equivalent", passage.text, re.I)
        )
        # Running navigation headings often say 'Contents' on EVERY PDF page.
        # Do not mistake a quantified emissions table for the table of contents.
        if re.search(r"\b(index|contents)\b", section) and not emissions_table:
            score -= 20
        if scope and scope[1] in {"1", "2"}:
            own_operations = bool(
                re.search(r"\bown operations\b|\bexcluding financed emission\b", text)
            )
            financed = bool(
                re.search(r"\bfinanced emission\b|\bpcaf\b|\bcredit lending\b", text)
            )
            if financed and not own_operations:
                # Counterparty Scope 1/2 inside a bank's financed emissions is
                # NOT the bank's own Scope 1/2. Retain it as a lower candidate.
                score -= 30
            if own_operations:
                score += 8
        if metric.evidence_kind == "performance" and re.search(
            r"\b(targets?|ambition|roadmap)\b", section
        ):
            score -= 8
        result.append(Retrieved(passage, round(score, 4), matches))
    return sorted(
        result,
        key=lambda item: (-item.score, item.passage.page, str(item.passage.chunk_id)),
    )[:top_k]
