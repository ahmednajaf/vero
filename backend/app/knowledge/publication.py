"""Package research, calculation and editorial stages in the existing saved run."""
import hashlib
import json
import re
from decimal import Decimal
from typing import Any

from pydantic import Field
from sqlalchemy import Engine

from app.core.config import Settings
from app.knowledge import report_prompts as prompts
from app.knowledge.provider import ResearchError, StructuredProvider
from app.knowledge.research import factual_number_tokens, number_tokens
from app.knowledge.grounding import number
from app.extraction.units import parse_unit
from app.knowledge.synthesis import INSTRUCTIONS, StrictModel, research_packet, synthesise
from app.llm.contracts import ExtractionError, Prompt
from app.llm.openai import OpenAIStructuredExtractor


class Paragraph(StrictModel):
    heading: str = Field(min_length=5, max_length=140)
    takeaway: str = Field(min_length=15, max_length=240)
    text: str = Field(min_length=15, max_length=1800)
    record_ids: list[str] = Field(min_length=1)


class Chapter(StrictModel):
    paragraphs: list[Paragraph]


def stage(identifier: str, title: str, kind: str, **data: Any) -> dict[str, Any]:
    return {"id": identifier, "title": title, "kind": kind, "status": "pending",
            "result": None, "error_code": None, **data}


def research_stages(topic_names: dict[str, str], ids: list[str]) -> list[dict[str, Any]]:
    # Each company gets a research slot even for a larger sector package. A single
    # global search previously sampled only six companies and lost the rest.
    groups = [ids[i:i + 5] for i in range(0, len(ids), 5)]
    return [stage(f"research:{topic}:{g}:{lens}", f"{name} · {lens}", "research",
                  topic_id=topic, company_ids=group, lens=lens)
            for topic, name in topic_names.items() for g, group in enumerate(groups)
            for lens in prompts.LENSES] + [stage("compile", "Preparing comparisons", "compile")]


def packets(definition: dict[str, Any], sections: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Partition ALL cited findings. Never silently drop the end of the report."""
    by_topic: dict[str, list[dict[str, Any]]] = {}
    titles: dict[str, str] = {}
    seen: set[str] = set()
    for section in sections:
        if section.get("kind") not in {None, "research"} or section["id"] == "synthesis":
            continue
        topic = section.get("topic_id", section["id"])
        titles[topic] = section["title"].split(" · ")[0]
        for claim in (section.get("result") or {}).get("claims", []):
            key = json.dumps([claim["text"].casefold(), sorted((c["evidence_id"], c["quote"]) for c in claim["citations"])])
            if key in seen:
                continue
            seen.add(key)
            by_topic.setdefault(topic, []).append(claim)
    result = []
    for topic, claims in by_topic.items():
        batch: list[dict[str, Any]] = []

        def build(items: list[dict[str, Any]]) -> dict[str, Any]:
            return research_packet(definition, [{"id": topic, "title": titles[topic], "result": {"claims": items}}], limit)

        for claim in claims:
            trial = build([*batch, claim])
            if trial["omitted_findings"] and batch:
                result.append({"topic_id": topic, "title": titles[topic], "packet": build(batch)})
                batch = []
            if build([claim])["omitted_findings"]:
                raise ResearchError("report_evidence_packet_too_large")
            batch.append(claim)
        if batch:
            result.append({"topic_id": topic, "title": titles[topic], "packet": build(batch)})
    return result


def editorial_stages(definition: dict[str, Any], sections: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    output = []
    for i, item in enumerate(packets(definition, sections, limit)):
        output.extend([
            stage(f"derive:{i}", f"{item['title']} · comparisons", "derive", **{k: item[k] for k in ("topic_id", "packet")}),
            stage(f"chapter:{i}", item["title"], "chapter", topic_id=item["topic_id"], depends_on=f"derive:{i}"),
        ])
    return output


def records_for(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = {}
    for i, insight in enumerate(result.get("insights", [])):
        records[f"I{i + 1}"] = {"text": f"{insight['headline']}. {insight['observation']} {insight['implication']}",
                                  "citations": insight["citations"]}
    for i, award in enumerate(result.get("awards", [])):
        if not award["rows"]:
            continue
        citations = [v["source"] for r in award["rows"] for v in r["inputs"]]
        records[f"C{i + 1}"] = {"calculation": award, "citations": citations}
    return records


def ground_chapter(output: Chapter, records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return ground_paragraphs([p.model_dump() for p in output.paragraphs], records)


def ground_paragraphs(items: list[dict[str, Any]], records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Check evidence independently of the presentation contract's text lengths.

    Callers validate their own contract first (Chapter or PeerAnalysis).
    """
    paragraphs, warnings = [], []
    for paragraph in items:
        if any(ref not in records for ref in paragraph['record_ids']):
            warnings.append("unknown_report_record")
            continue
        selected = [records[ref] for ref in dict.fromkeys(paragraph['record_ids'])]
        text = paragraph['heading'] + " " + paragraph['takeaway'] + " " + paragraph['text']
        citations = list({(s["evidence_id"], s["quote"]): s for record in selected for s in record["citations"]}.values())
        # The writer receives these bounded neighbouring passages as well as the
        # short quotation. Validate against the same supplied evidence, not a
        # narrower quote-only view that drops table years and footnotes.
        from app.knowledge.analytical import source_context
        permitted = number_tokens(" ".join(c["quote"] + ' ' + source_context(c) for c in citations))
        for record in selected:
            # Table headers often carry the unit/year outside a short cell quote.
            # Validated extraction records preserve these fields explicitly.
            for fact in record.get('reported_values', []):
                value = number(str(fact.get('value', '')))
                if value is None:
                    continue
                unit = parse_unit(fact.get('unit') or '')
                permitted |= number_tokens(format(value, 'f'))
                if unit and unit.symbol == '%':
                    permitted |= number_tokens(format(value, 'f') + '%')
                if fact.get('year'):
                    permitted |= number_tokens(str(fact['year']))
            calculation = record.get("calculation", {})
            # Formula constants are legitimate explanation inputs (e.g. the zero
            # reference in a subtraction), not missing corporate observations.
            for step in calculation.get('steps', []):
                for operand in step.get('operands', []):
                    if re.fullmatch(r'-?\d+(?:\.\d+)?', str(operand)):
                        permitted |= number_tokens(str(operand))
            for row in calculation.get("rows", []):
                if row.get('year'):
                    permitted |= number_tokens(str(row['year']))
                # Permit code-derived numbers: the old raw-quote-only check rejected
                # precisely the new metrics this product is supposed to explain.
                value = Decimal(row["value"])
                for places in range(4):
                    permitted |= number_tokens(f"{value:.{places}f}")
                    permitted |= number_tokens(f"{value:.{places}f}%")
                    if "ratio" in row.get("unit", "").lower() or row.get("unit") == "fraction":
                        permitted |= number_tokens(f"{value * 100:.{places}f}%")
                    # "Fell 8.6%" is the verbal form of a calculated -8.6%,
                    # not an unsupported new result. Keep the signed value in data.
                    if value < 0 and re.search(r'\b(fell|declin\w*|reduc\w*|lower|fewer|gap|below)\b', text, re.I):
                        permitted |= number_tokens(f"{abs(value):.{places}f}%")
                        permitted |= number_tokens(f"{abs(value):.{places}f}")
                for operand in row.get('inputs', []):
                    if operand.get('year'):
                        permitted |= number_tokens(str(operand['year']))
                    for field in ('value', 'raw_value'):
                        original = number(str(operand.get(field, '')))
                        if original is None:
                            continue
                        permitted |= number_tokens(format(original, 'f'))
                        # Readability conversions in prose: 33,100,000 tonnes
                        # may be written as 33.1 million tonnes. No new arithmetic.
                        for word, scale in (('thousand', 1000), ('million', 1000000), ('billion', 1000000000)):
                            if re.search(rf'\b{word}\b', text, re.I):
                                permitted |= number_tokens(format(original / scale, 'f'))
            permitted |= number_tokens(f"{calculation.get('sample_size', '')} {calculation.get('cohort_size', '')}")
        if not factual_number_tokens(text, citations).issubset(permitted):
            warnings.append("report_number_not_supported")
            continue
        paragraphs.append({**paragraph, "citations": citations})
    if records and not paragraphs:
        raise ResearchError("report_editorial_grounding_failed")
    return {"status": "partial" if warnings else "answered", "paragraphs": paragraphs,
            "claims": [{"text": f"{p['heading']} — {p['text']}", "citations": p["citations"]} for p in paragraphs],
            "validation": {"warnings": warnings}, "coverage": {}, "notes": []}


async def execute(engine: Engine, definition: dict[str, Any], section: dict[str, Any], sections: list[dict[str, Any]], settings: Settings, provider: StructuredProvider | None) -> dict[str, Any]:
    package = prompts.PACKAGES[definition["package"]]
    if section["kind"] == "derive":
        return await synthesise(engine, definition, [], settings, provider, packet=section["packet"],
                                instructions=INSTRUCTIONS + "\nPACKAGE BRIEF:\n" + str(package["brief"]))
    parent = next(s for s in sections if s["id"] == section["depends_on"])
    records = records_for(parent["result"])
    if not records:
        return {"status": "insufficient_evidence", "claims": [], "paragraphs": [], "notes": [], "coverage": {}}
    adapter = OpenAIStructuredExtractor(settings, engine, provider, instructions=prompts.EDITOR,
                                       instruction_version=prompts.VERSION, task_type="report_chapter")
    packet = {"package_brief": package["brief"], "companies": definition["companies"],
              "topic": section["title"], "records": records}
    try:
        completion = await adapter.extract_structured(Prompt("client-report-chapter", prompts.VERSION, json.dumps(packet, sort_keys=True)), Chapter)
    except ExtractionError as exc:
        raise ResearchError(exc.code) from None
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from app.db.models import KnowledgeAnswer
    with Session(engine) as session:
        ledger = session.scalar(select(KnowledgeAnswer).where(KnowledgeAnswer.payload["prompt_sha256"].astext == completion.prompt_sha256,
                                                             KnowledgeAnswer.payload["schema_sha256"].astext == completion.schema_sha256,
                                                             KnowledgeAnswer.model == completion.model,
                                                             KnowledgeAnswer.status == "completed").order_by(KnowledgeAnswer.created_at.desc()).limit(1))
        accounting = {"estimated_cost_usd": str(ledger.charged_usd), "usage": ledger.usage} if ledger else {}
    return {**ground_chapter(completion.data, records), **accounting, "model": completion.model,
            "cached": completion.attempts == 0, "latency_ms": completion.latency_ms,
            "prompt_version": prompts.VERSION, "prompt_sha256": completion.prompt_sha256}


def completed_editorial_topics(sections: list[dict[str, Any]]) -> set[str]:
    """A partial chapter must never hide the remainder of a topic's research."""
    topics = {s.get("topic_id") for s in sections if s.get("kind") == "chapter"}
    return {topic for topic in topics if topic and all(
        (s.get("result") or {}).get("paragraphs")
        for s in sections if s.get("kind") == "chapter" and s.get("topic_id") == topic
    )}


def display_metrics(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One presentation per executed relationship; keep raw proposals in JSON."""
    distinct: dict[str, dict[str, Any]] = {}
    def unit(value: str) -> str:
        if value.lower() in {'p.p.', 'percentage points', 'pp'}:
            return 'percentage points'
        parsed = parse_unit(value)
        return parsed.symbol if parsed else value.lower()

    for section in sections:
        result = section.get('result') or {}
        for original in result.get('awards', []) + result.get('metrics', []):
            if not original['rows']:
                continue
            rows = []
            for row in original['rows']:
                operands = sorted((str(i['source']['report_id']), i['source']['page'], str(i.get('year') or ''),
                                   str(number(str(i.get('raw_value', '')))), unit(i['raw_unit']))
                                  for i in row['inputs'])
                rows.append((row['company_id'], str(Decimal(row['value']).normalize()), unit(row['unit']), row.get('year'), operands))
            key = json.dumps(sorted(rows), sort_keys=True)
            if key in distinct:
                distinct[key]['equivalent_ids'].append(original.get('id'))
                continue
            # Preserve these useful within-company changes, but do not derive a
            # peer median or winner when the model explicitly reports unlike bases.
            contextual = original.get('contextual', False) or bool(re.search(r'\bdirectional\b|not.{0,35}rank|not the same.{0,30}populations', original.get('caveat', ''), re.I))
            distinct[key] = {**original, 'equivalent_ids': [original.get('id')], 'contextual': contextual,
                             **({'direction': 'none', 'winner_ids': []} if contextual else {})}
    displayed = list(distinct.values())
    counts: dict[str, int] = {}
    for metric in displayed:
        name = metric['name'].strip().casefold()
        counts[name] = counts.get(name, 0) + 1
    for metric in displayed:
        if counts[metric['name'].strip().casefold()] > 1:
            direct = all(len(r['inputs']) == 1 for r in metric['rows'])
            metric['name'] += ' · reported' if direct else ' · calculated'
    # Lead with actual peer comparisons. A one-company calculation remains
    # available, but must not displace a supported multi-company chart.
    return sorted(displayed, key=lambda m: -len({r['company_id'] for r in m['rows']}))


def display_badges(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Freeze the first supported rubric for each named edition distinction.

    A continuation may add a new distinction, not silently change an existing
    award's rubric and announce contradictory winners under the same name.
    Rejected/repeated proposals remain in the saved analysis JSON.
    """
    distinct: dict[str, dict[str, Any]] = {}
    for section in sections:
        for badge in (section.get('result') or {}).get('badges', []):
            if not badge['winner_ids'] or not badge['rows']:
                continue
            if badge['basis'] == 'qualitative':
                if not any(Decimal(r['value']) > 0 for r in badge['rows']):
                    continue
                # Ordinal timing is not established by a qualitative points sum.
                if re.search(r'\b(earliest|fastest|latest)\b', badge['name'], re.I):
                    continue
            distinct.setdefault(badge['name'].strip().casefold(), badge)
    return list(distinct.values())


def document(payload: dict[str, Any]) -> dict[str, Any]:
    """One export/read model; no AI, database changes or mutations on GET."""
    chapters: list[dict[str, Any]] = []
    awards = display_metrics(payload['sections'])
    citations: dict[str, Any] = {}
    seen: set[str] = set()
    sections = payload["sections"]
    authored_topics = completed_editorial_topics(sections)
    badges = display_badges(sections)
    badge_ids = {a['id'] for a in badges}
    rejected: set[str] = set()
    conflicted_award_sections: set[str] = set()
    for s in sections:
        result = s.get('result') or {}
        rejected.update(m['id'] for m in result.get('metrics', []) if not m['rows'])
        rejected.update(a['id'] for a in result.get('badges', []) if a['id'] not in badge_ids)
        if any(a['id'] not in badge_ids for a in result.get('badges', [])):
            conflicted_award_sections.add(s['id'])
        rejected.update(f['id'] for f in result.get('analytical_findings', []) if any(m in rejected for m in f['metric_ids']))

    def eligible(paragraph: dict[str, Any], section: dict[str, Any]) -> bool:
        if rejected.intersection(paragraph.get('record_ids', [])):
            return False
        parent = section.get('analysis_id', section['id'])
        # Prose about a discarded award rubric must not contradict the frozen
        # edition's winner. Keep the underlying source records in the audit JSON.
        if parent in conflicted_award_sections and re.search(
            r'\b(?:this award|the award|award (?:outcome|scor\w*|goes)|wins the|winner\w*|won this)\b',
            paragraph['text'], re.I):
            return False
        return True

    published = {ref for s in sections if s.get("kind") == "publish"
                 for p in (s.get("result") or {}).get("paragraphs", []) if eligible(p, s)
                 for ref in p.get("record_ids", [])}
    analytical_results = [s["result"] for s in sections if s.get("kind") == "analyse" and s.get("result")]
    analysis: dict[str, Any] = {**(analytical_results[0] if analytical_results else {}),
        "badges": badges}
    if payload['definition'].get('companies') and any(s.get('kind') == 'collect' and (s.get('result') or {}).get('company_id') for s in sections):
        from app.knowledge.analytical import collection_summary
        analysis.update(payload.get('analysis_summary') or collection_summary(sections, payload['definition']['companies']))
    # The workbook includes the entire collected ledger, not just operands chosen
    # for the first two calculations. Source excerpts remain in the evidence view.
    reported: dict[str, Any] = {}
    for section in sections:
        if section.get("kind") not in {"collect", "check"}:
            continue
        for fact in (section.get("result") or {}).get("facts", []):
            key = json.dumps([fact.get(k) for k in ("company_id", "metric", "value", "unit", "year", "population")])
            reported.setdefault(key, fact)
    written_records: set[str] = set()
    for section in sections:
        result = section.get("result") or {}
        if section.get("kind") in {"derive", "compile", "collect", "check"} or (section.get("kind") == "research" and section.get("topic_id") in authored_topics):
            continue
        paragraphs = result.get("paragraphs")
        if section.get("kind") == "analyse":
            paragraphs = [{"heading": f["headline"], "takeaway": f["takeaway"], "text": f["explanation"] + " " + f["business_implication"], "citations": f["citations"], 'record_ids': [f['id']]}
                          for f in result.get("analytical_findings", []) if f["id"] not in published]
        if paragraphs is None:
            paragraphs = []
            for claim in result.get("claims", []):
                heading, sep, body = claim["text"].partition(" — ")
                paragraphs.append({"heading": heading if sep else "", "text": body if sep else heading,
                                   "citations": claim["citations"]})
        unique = []
        section_records: set[str] = set()
        for paragraph in paragraphs:
            if not eligible(paragraph, section):
                continue
            refs_written = set(paragraph.get('record_ids', []))
            if section.get('kind') == 'publish' and refs_written and refs_written <= written_records:
                continue
            key = paragraph["text"].strip().casefold()
            if key in seen:
                continue
            seen.add(key)
            refs = []
            for source in paragraph["citations"]:
                key_source = f"{source.get('report_id')}:{source.get('page')}"
                if key_source not in citations:
                    citations[key_source] = {**source, "reference": len(citations) + 1}
                refs.append(citations[key_source]["reference"])
            unique.append({**paragraph, "references": list(dict.fromkeys(refs))})
            section_records.update(refs_written)
        # Earlier saved writers sometimes rewrote records assigned to a different
        # publishing batch. Keep one edition per record, not every rewrite. A
        # coherent multi-paragraph treatment within that first batch is retained.
        # New analytical records remain eligible; raw variants stay in the JSON.
        if section.get('kind') == 'publish':
            written_records.update(section_records)
        if unique:
            title = section['title']
            if section.get('kind') in {'analyse', 'publish'}:
                from app.knowledge.analytical import LENSES
                parent = section if section.get('kind') == 'analyse' else next((s for s in sections if s['id'] == section.get('analysis_id')), {})
                title = LENSES.get(parent.get('lens'), ('Peer insights', set()))[0]
            chapters.append({"id": section["id"], "title": title, "paragraphs": unique})
    for award in awards:
        for row in award["rows"]:
            for item in row["inputs"]:
                source = item["source"]
                key = f"{source.get('report_id')}:{source.get('page')}"
                if key not in citations:
                    citations[key] = {**source, "reference": len(citations) + 1}
    for source in [s for a in analysis.get("badges", []) for r in a["rows"] for s in r["sources"]] + [s for p in analysis.get("promises", []) for s in p["citations"]]:
        key = f"{source.get('report_id')}:{source.get('page')}"
        if key not in citations:
            citations[key] = {**source, "reference": len(citations) + 1}
    package = payload["definition"].get("package")
    grouped: dict[str, dict[str, Any]] = {}
    for chapter in chapters:
        key = chapter['title'].strip().casefold()
        if key not in grouped:
            grouped[key] = {**chapter, 'paragraphs': list(chapter['paragraphs'])}
        else:
            grouped[key]['paragraphs'].extend(chapter['paragraphs'])
    chapters = list(grouped.values())
    promises = list({(p['company_id'], p['commitment'].strip().casefold(), p.get('deadline')): p
                     for p in analysis.get('promises', [])}.values())
    return {"title": payload["title"], "package": prompts.PACKAGES.get(package, {}).get("name", "Peer analysis"),
            "incomplete": any(s.get("status") not in {None, "completed"} for s in sections),
            "authored": bool(authored_topics or published), "chapters": chapters, "awards": awards,
            "badges": analysis.get("badges", []), "disclosure_scores": analysis.get("disclosure_scores"),
            "promises": promises,
            "reported_facts": list(reported.values()),
            "references": list(citations.values()), "findings_count": sum(len(c["paragraphs"]) for c in chapters),
            "fingerprint": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}
