"""Cited AI synthesis; never writes to the validated metric dataset."""

import hashlib
import json
import logging
import re
import time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.knowledge.budget import check_limits
from app.db.models import Company, KnowledgeAnswer
from app.knowledge.contracts import (
    AskRequest,
    ResearchOutput,
    ResearchPlan,
    SearchRequest,
)
from app.knowledge.planning import (
    conversation,
    resolve_scope,
    planning_context,
    corpus_signature,
    benchmark_context,
)
from app.knowledge.provider import (
    PROMPT_VERSION,
    OpenAIResearchProvider,
    ResearchError,
    ResearchProvider,
    configured,
    request_body,
)
from app.knowledge.search import (
    adjacent_text_candidates,
    balanced_candidates,
    company_scope,
    coverage,
    indexed_sources,
)

LOG = logging.getLogger(__name__)
LIMITATION = "AI synthesis of selected passages, not a verified fact set or exhaustive disclosure assessment. Citations are mechanically checked; their presence does not prove the interpretation."


def normalise(value: str) -> str:
    return " ".join(value.split())


def number_tokens(value: str) -> set[str]:
    """Canonical numeric spelling only: no arithmetic or percent/fraction conversion.

    Ignore sentence punctuation; preserve negatives and percent dimensions. Commas
    are thousands separators only when arranged in groups of three. FY2024 can
    support the literal year 2024, but FY24 is not guessed into a century.
    """
    value = re.sub(r"\bFY\s*(\d{4})\b", r"\1", value, flags=re.I).replace("−", "-")
    found = re.findall(
        r"(?<!\w)([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(\s*(?:%|percent\b|per cent\b))?",
        value,
        re.I,
    )
    return {
        format(Decimal(number.replace(",", "")).normalize(), "f")
        + ("%" if percent else "")
        for number, percent in found
    }


def factual_number_tokens(text: str, citations: list[dict[str, Any]]) -> set[str]:
    """Separate verified citation locators and scope identifiers from quantities.

    A page number is checked against source metadata, never against PDF prose.
    Scope labels are checked against the cited passage's context; this allows a
    short quote of a table row while its header remains in the same source chunk.
    Neither rule authorises a new value, arithmetic, or an inferred scope.
    """
    pages = {int(c["page"]) for c in citations if c.get("page") is not None}
    unsupported_labels: set[str] = set()

    def page_ref(match: re.Match[str]) -> str:
        page = int(match.group(1))
        if page not in pages:
            unsupported_labels.add(f"page:{page}")
        return " "

    text = re.sub(r"\b(?:page|p\.)\s*(\d+)\b", page_ref, text, flags=re.I)
    context = " ".join(c.get("text", c.get("quote", "")) for c in citations)
    scope_pattern = (
        r"\bscopes?\s*([123](?:\s*(?:,?\s*and|&|/|\+|,)\s*(?:scope\s*)?[123])*)\b"
    )
    supported_scopes = {
        identifier
        for match in re.finditer(scope_pattern, context, flags=re.I)
        for identifier in re.findall(r"[123]", match.group(1))
    }

    def scopes(match: re.Match[str]) -> str:
        for identifier in re.findall(r"[123]", match.group(1)):
            if identifier not in supported_scopes:
                unsupported_labels.add(f"scope:{identifier}")
        return "scope identifier"

    text = re.sub(scope_pattern, scopes, text, flags=re.I)
    return number_tokens(text) | unsupported_labels


def validate_claims(
    output: ResearchOutput, sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if (output.status in {"answered", "partial"}) != bool(output.claims):
        raise ResearchError("answer_status_conflict")
    by_id = {s["evidence_id"]: s for s in sources}
    claims = []
    for claim in output.claims:
        citations = []
        for citation in claim.citations:
            source = by_id.get(citation.evidence_id)
            if source is None or normalise(citation.quote) not in normalise(
                source["text"]
            ):
                raise ResearchError("unsupported_citation")
            citations.append({**source, "quote": citation.quote})
        quoted = " ".join(c["quote"] for c in citations)

        # Deterministic numerical grounding is an extra guard, not semantic verification.
        if not factual_number_tokens(claim.text, citations).issubset(
            number_tokens(quoted)
        ):
            raise ResearchError("unsupported_number")
        if re.search(
            r"\bpeer (?:percentile|median)|\beligible peer cohort|\b(?:supplied |our |the )benchmark (?:found|calculated|shows)",
            claim.text,
            re.I,
        ):
            raise ResearchError("calculation_requires_structured_source")
        if re.search(
            r"\b(overall (?:winner|leader)|most sustainable|winning the race|wins the race|best sustainability performer)\b",
            claim.text,
            re.I,
        ):
            raise ResearchError("unsupported_overall_ranking")
        if re.search(
            r"\b(all|most|none of|majority of) (?:the |these |peer )?(companies|peers|reports)\b|\b\d+\s*(?:%|percent)\s+of\s+(?:the )?(?:companies|peers)|\b\d+\s+(?:out )?of\s+\d+\s+(?:companies|peers)",
            claim.text,
            re.I,
        ):
            raise ResearchError("population_claim_requires_assessment")
        claims.append({"text": claim.text, "citations": citations})
    return claims


def packet(
    session: Session,
    request: AskRequest,
    settings: Settings,
    plan: ResearchPlan | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    scope = request.model_dump(mode="json", exclude={"question", "parent_answer_id"})
    previous_questions = conversation(session, request)
    # Prior user questions resolve follow-ups. Old generated claims are NEVER facts.
    retrieval_query = request.question[:400]
    if previous_questions:
        retrieval_query += " " + previous_questions[-1][:199]
    effective, resolution = (
        resolve_scope(session, request, plan) if plan else (request, {})
    )
    queries = (
        ([] if plan.intent == "library_coverage" else plan.queries)
        if plan
        else [retrieval_query[:600]]
    )
    # Reciprocal-rank fusion balances complementary query facets. Scores from
    # different lexical queries are not directly comparable.
    merged: dict[str, dict[str, Any]] = {}
    company_counts: dict[str, int] = {}
    fusion: dict[str, float] = {}
    query_trace = []
    for query in queries:
        found = balanced_candidates(
            session,
            SearchRequest(
                **effective.model_dump(exclude={"question", "parent_answer_id"}),
                query=query[:600],
            ),
        )
        query_trace.append(
            {
                "query": query,
                "matching_passages": found["total"],
                "companies": len(found["company_counts"]),
            }
        )
        for identifier, count in found["company_counts"].items():
            company_counts[identifier] = max(count, company_counts.get(identifier, 0))
        for rank, source in enumerate(
            sorted(found["items"], key=lambda s: (-s["score"], s["evidence_id"]))
        ):
            identifier = source["evidence_id"]
            merged[identifier] = source
            fusion[identifier] = fusion.get(identifier, 0) + 1 / (30 + rank)
    found = {
        "items": sorted(
            merged.values(), key=lambda s: (-fusion[s["evidence_id"]], s["evidence_id"])
        ),
        "total": sum(company_counts.values()),
        "company_counts": company_counts,
    }
    # Round-robin companies to stop a long report dominating cross-company research.
    groups: dict[str, list[dict[str, Any]]] = {}
    for source in found["items"]:
        # Font/bounding-box heading metadata can dwarf the actual page text. It is
        # still available from /evidence, but never competes with peer evidence.
        item = {key: value for key, value in source.items() if key != "headings"}
        groups.setdefault(item["company_id"], []).append(item)
    # A broad query samples the most relevant company evidence, not the first
    # alphabetical names. Bound breadth so each example can also supply depth.
    eligible_groups = list(groups.values())[:6] if plan else list(groups.values())
    selected: list[dict[str, Any]] = []
    used_evidence: set[str] = set()
    used = 0
    for depth in range(8):
        if depth == 1:
            # After every company gets a first chance, reserve nearby context before
            # filling the remaining budget with unrelated high-frequency passages.
            for source in adjacent_text_candidates(session, effective, list(selected)):
                item = {
                    key: value for key, value in source.items() if key != "headings"
                }
                length = len(
                    json.dumps(
                        model_evidence(item) if plan else item, ensure_ascii=False
                    )
                )
                if (
                    item["evidence_id"] not in used_evidence
                    and used + length <= settings.knowledge_max_evidence_chars
                    and len(selected) < 16
                ):
                    selected.append(item)
                    used += length
                    used_evidence.add(item["evidence_id"])
        for group in eligible_groups:
            if depth >= len(group):
                continue
            item = group[depth]
            if item["evidence_id"] in used_evidence:
                continue
            length = len(
                json.dumps(model_evidence(item) if plan else item, ensure_ascii=False)
            )
            if (
                used + length > settings.knowledge_max_evidence_chars
                or len(selected) >= 16
            ):
                continue
            selected.append(item)
            used += length
            used_evidence.add(item["evidence_id"])
    indexed_ids = set(
        session.scalars(indexed_sources(effective).with_only_columns(Company.id))
    )
    supplied = {s["company_id"] for s in selected}
    companies = list(
        session.scalars(
            select(Company)
            .where(*company_scope(effective))
            .order_by(Company.company_name, Company.id)
        )
    )
    assessments = [
        {
            "company_id": str(c.id),
            "company": c.company_name,
            "matching_passages": found["company_counts"].get(str(c.id), 0),
            "status": "metadata_count_only"
            if plan and plan.intent == "library_coverage"
            else "supplied"
            if str(c.id) in supplied
            else "omitted_context_limit"
            if str(c.id) in groups
            else "no_lexical_match"
            if c.id in indexed_ids
            else "not_indexed_in_scope",
        }
        for c in companies
    ]
    in_scope = {c.id for c in companies}
    assessments.extend(
        {
            "company_id": str(identifier),
            "company": None,
            "matching_passages": 0,
            "status": "not_in_active_library_scope",
        }
        for identifier in sorted(set(effective.company_ids) - in_scope, key=str)
    )
    return {
        "question": request.question,
        "scope": scope,
        "previous_questions": previous_questions,
        "evidence": selected,
        **(
            {
                "research_plan": plan.model_dump(),
                "retrieval_scope": resolution,
                "benchmark": benchmark_context(session, effective, plan),
            }
            if plan
            else {}
        ),
    }, {
        **coverage(session, effective),
        "matching_passages": found["total"],
        "passages_supplied": len(selected),
        "companies_supplied": len({s["company_id"] for s in selected}),
        "selection": "multi_query_relevance_balanced_same_page_v4",
        "queries": query_trace,
        "match_count_meaning": "Sum of per-company maximum query matches; overlapping multi-query matches are not a disclosure count.",
        "companies": assessments,
        "evidence_characters": used,
        "max_evidence_characters": settings.knowledge_max_evidence_chars,
        "meaning": "Retrieval coverage, not disclosure completeness. No lexical match does not mean not reported. Companies omitted by the context budget are explicit.",
        "exhaustive": False,
    }


def model_evidence(source: dict[str, Any]) -> dict[str, Any]:
    """Only the model context is compacted; complete provenance stays server-side."""
    return {
        key: source[key]
        for key in (
            "evidence_id",
            "company",
            "company_id",
            "report",
            "report_id",
            "page",
            "text",
            "document_role",
            "reporting_year",
            "detected_year",
            "kind",
        )
        if key in source
    }


def answer_notes(
    plan: ResearchPlan,
    payload: dict[str, Any],
    counts: dict[str, Any],
    output: ResearchOutput,
    withheld: list[str],
) -> list[str]:
    """Scope/capability statements come from server state, never uncited model facts."""
    notes = []
    benchmark = payload.get("benchmark")
    if benchmark and benchmark.get("status") == "no_eligible_peer_cohort":
        notes.append(
            "The benchmark database has no eligible peer cohort for this measure and year, so peer percentiles are unavailable. Reported figures can still be discussed with their source boundaries."
        )
    if plan.intent == "ranking":
        notes.append(
            "These are reported examples, not an overall sustainability ranking. A leader can only be established for a defined measure and comparable scope, baseline and reporting period."
        )
    elif plan.intent == "disclosure_coverage":
        notes.append(
            "This search can show disclosures found for named companies, but cannot establish a complete peer disclosure count. A missing match is not proof of non-disclosure."
        )
    if (
        counts["companies_in_scope"] > counts["companies_supplied"]
        and counts["companies_supplied"]
    ):
        notes.append(
            f"Evidence supplied for {counts['companies_supplied']} of {counts['companies_in_scope']} companies in scope; examples were selected by retrieval relevance, not sustainability performance."
        )
    unresolved = payload.get("retrieval_scope", {}).get("unresolved_companies", [])
    if unresolved:
        notes.append(
            "Could not resolve within the selected library scope: "
            + ", ".join(c["name"] for c in unresolved)
            + ". Select the intended companies or adjust the peer scope."
        )
    if payload.get("retrieval_scope", {}).get("invalid_filters"):
        notes.append(
            "The requested country or sector is not present in the selected library scope."
        )
    if not payload["evidence"] and plan.intent != "library_coverage":
        notes.append(
            "No matching source passages were found for this research plan. This does not establish that the information is absent from the reports."
        )
    labels = {
        "incompatible_comparison": "The cited definitions or reporting periods differ; the reported figures are not a like-for-like performance comparison.",
        "target_not_achievement": "Target dates describe commitments, not achieved reductions.",
        "missing_evidence": "The retrieved evidence does not resolve every part of the question.",
    }
    notes.extend(labels[k] for k in output.limitations if k in labels)
    if withheld:
        notes.append(
            "Some draft statements failed source checks and were withheld; only the supported statements are shown."
        )
    return list(dict.fromkeys(notes))


def preview(
    session: Session, request: AskRequest, settings: Settings
) -> dict[str, Any]:
    """Non-AI lexical preview. The paid, planned workflow may retrieve other evidence."""
    from app.knowledge.inspection import inspect_source

    payload, scope_coverage = packet(session, request, settings)
    report_ids = list(dict.fromkeys(s["report_id"] for s in payload["evidence"]))
    return {
        "payload": payload,
        "coverage": scope_coverage,
        "source_checks": [
            inspect_source(session, UUID(i), settings) for i in report_ids
        ],
        "model_called": False,
        "preview_type": "lexical_only_not_final_ai_research_plan",
        "configuration_error": configured(settings),
        "limitation": LIMITATION,
    }


async def ask(
    session: Session,
    request: AskRequest,
    settings: Settings,
    provider: ResearchProvider | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    context = planning_context(session, request)
    signature = corpus_signature(session, request)
    cache_key = hashlib.sha256(
        json.dumps(
            [
                PROMPT_VERSION,
                settings.openai_model,
                settings.openai_reasoning_effort,
                settings.openai_max_output_tokens,
                str(request.parent_answer_id) if request.parent_answer_id else None,
                settings.knowledge_max_evidence_chars,
                context,
                signature,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cached = session.scalar(
        select(KnowledgeAnswer)
        .where(
            KnowledgeAnswer.request_sha256 == cache_key,
            KnowledgeAnswer.status == "completed",
        )
        .order_by(KnowledgeAnswer.created_at.desc())
        .limit(1)
    )
    if cached:
        return {
            **cached.payload,
            "cached": True,
            "model_called": False,
            "answer_id": str(cached.id),
        }
    reason = configured(settings)
    if reason:
        raise ResearchError(reason)
    # Deliberately conservative token upper estimate; not a reported actual token count.
    planner_bound = (
        len(
            json.dumps(
                request_body(settings, context, planning=True), ensure_ascii=False
            ).encode()
        )
        + 4096
    )
    # UTF-8 worst-case plus bounded plan/tool/schema metadata. Actual request bytes
    # are checked before synthesis. No unbudgeted planner or repair calls.
    synthesis_bound = settings.knowledge_max_evidence_chars * 4 + 40000
    input_bound = planner_bound + synthesis_bound
    output_bound = (
        min(2000, settings.openai_max_output_tokens) + settings.openai_max_output_tokens
    )
    reservation = (
        Decimal(input_bound) * Decimal(str(settings.openai_input_price))
        + Decimal(output_bound) * Decimal(str(settings.openai_output_price))
    ) / 1_000_000
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('knowledge-budget', 0))")
    )
    # Another identical request may have completed while we acquired the lock.
    cached = session.scalar(
        select(KnowledgeAnswer)
        .where(
            KnowledgeAnswer.request_sha256 == cache_key,
            KnowledgeAnswer.status == "completed",
        )
        .limit(1)
    )
    if cached:
        cached_payload = {
            **cached.payload,
            "cached": True,
            "model_called": False,
            "answer_id": str(cached.id),
        }
        session.rollback()
        return cached_payload
    try:
        check_limits(session, settings, reservation, input_bound + output_bound)
    except ResearchError:
        session.rollback()
        raise
    if session.scalar(
        select(KnowledgeAnswer.id).where(KnowledgeAnswer.status == "running").limit(1)
    ):
        session.rollback()
        raise ResearchError("research_busy_or_interrupted")
    saved = KnowledgeAnswer(
        request_sha256=cache_key,
        question=request.question,
        provider="openai",
        model=settings.openai_model,
        status="running",
        reserved_usd=reservation,
        usage={"reserved_tokens": input_bound + output_bound},
    )
    session.add(saved)
    session.commit()  # Reserve durably BEFORE any paid call; unknown outcomes retain reservation.
    identifier = saved.id
    calls: list[dict[str, Any]] = []

    def record(result: Any, stage: str) -> None:
        calls.append(
            {
                "stage": stage,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "latency_ms": round(result.latency_ms, 2),
                "model": result.model,
            }
        )
        # Unknown later outcomes retain the FULL reservation. Known usage is still
        # inspectable even if retrieval or a subsequent provider call fails.
        saved.usage = {**(saved.usage or {}), "calls": list(calls)}
        session.commit()

    try:
        client = provider or OpenAIResearchProvider(settings)
        planned = await client.plan(context)
        record(planned, "planning")
        if not isinstance(planned.data, ResearchPlan):
            raise ResearchError("invalid_research_plan")
        if planned.input_tokens > planner_bound or planned.output_tokens > min(
            2000, settings.openai_max_output_tokens
        ):
            raise ResearchError("provider_exceeded_token_bound")
        plan = planned.data
        retrieval_started = time.monotonic()
        payload, scope_coverage = packet(session, request, settings, plan)
        retrieval_ms = round((time.monotonic() - retrieval_started) * 1000, 2)
        saved.payload = {
            "stage": "retrieved",
            "research_plan": plan.model_dump(),
            "coverage": scope_coverage,
            "request_scope": context["selected_scope"],
        }
        session.commit()
        calculations = []
        claims: list[dict[str, Any]]
        withheld: list[str]
        unmatched_numbers: set[str] = set()
        if plan.intent == "library_coverage":
            # These are exact database counts, not AI-inferred disclosure coverage.
            calculations = [
                {
                    "label": label,
                    "value": scope_coverage[key],
                    "source": "/api/knowledge/status",
                }
                for key, label in (
                    ("companies_in_scope", "Companies in the selected library scope"),
                    (
                        "companies_with_indexed_reports",
                        "Companies with searchable reports",
                    ),
                    ("official_reports_downloaded", "Retained official PDFs"),
                    ("reports_indexed", "Searchable reports"),
                )
            ]
            output = ResearchOutput(status="answered", claims=[])
            claims, withheld = [], []
        elif not payload["evidence"]:
            output = ResearchOutput(
                status="insufficient_evidence",
                claims=[],
                limitations=["missing_evidence"],
            )
            claims, withheld = [], []
        else:
            model_payload = {
                **payload,
                "evidence": [model_evidence(s) for s in payload["evidence"]],
            }
            if (
                len(
                    json.dumps(
                        request_body(settings, model_payload), ensure_ascii=False
                    ).encode()
                )
                + 4096
                > synthesis_bound
            ):
                raise ResearchError("research_context_too_large")
            result = await client.analyse(model_payload)
            record(result, "synthesis")
            if not isinstance(result.data, ResearchOutput):
                raise ResearchError("openai_malformed_output")
            output = result.data
            if (output.status in {"answered", "partial"}) != bool(output.claims):
                raise ResearchError("answer_status_conflict")
            claims, withheld = [], []
            # Check independent statements separately. Unsupported drafts are NEVER
            # displayed, but need not destroy unrelated, correctly sourced findings.
            for claim in output.claims:
                try:
                    claims.extend(
                        validate_claims(
                            ResearchOutput(status="answered", claims=[claim]),
                            payload["evidence"],
                        )
                    )
                except ResearchError as exc:
                    withheld.append(exc.code)
                    if exc.code == "unsupported_number":
                        evidence_by_id = {
                            e["evidence_id"]: e for e in payload["evidence"]
                        }
                        unmatched_numbers.update(
                            factual_number_tokens(
                                claim.text,
                                [
                                    {
                                        **evidence_by_id.get(c.evidence_id, {}),
                                        "quote": c.quote,
                                    }
                                    for c in claim.citations
                                ],
                            )
                            - number_tokens(" ".join(c.quote for c in claim.citations))
                        )
            if withheld:
                output = output.model_copy(
                    update={"status": "partial" if claims else "insufficient_evidence"}
                )
        notes = answer_notes(plan, payload, scope_coverage, output, withheld)
        if (
            notes
            and claims
            and output.status == "answered"
            and plan.intent in {"ranking", "disclosure_coverage"}
        ):
            output = output.model_copy(update={"status": "partial"})
        usage: dict[str, object] = {
            "reserved_tokens": input_bound + output_bound,
            "input_tokens": sum(c["input_tokens"] for c in calls),
            "output_tokens": sum(c["output_tokens"] for c in calls),
            "latency_ms": round(sum(c["latency_ms"] for c in calls), 2),
            "retrieval_ms": retrieval_ms,
            "total_latency_ms": round((time.monotonic() - started) * 1000, 2),
            "actual_model": calls[-1]["model"],
            "calls": calls,
            "input_usd_per_million": settings.openai_input_price,
            "output_usd_per_million": settings.openai_output_price,
        }
        cost = (
            Decimal(str(usage["input_tokens"]))
            * Decimal(str(settings.openai_input_price))
            + Decimal(str(usage["output_tokens"]))
            * Decimal(str(settings.openai_output_price))
        ) / 1_000_000
        saved.usage, saved.charged_usd = usage, cost
        if (
            int(str(usage["input_tokens"])) > input_bound
            or int(str(usage["output_tokens"])) > output_bound
        ):
            raise ResearchError("provider_exceeded_token_bound")
        answer: dict[str, Any] = {
            "question": request.question,
            "request_scope": payload["scope"],
            "parent_answer_id": str(request.parent_answer_id)
            if request.parent_answer_id
            else None,
            "status": output.status,
            "claims": claims,
            "coverage": scope_coverage,
            "research_plan": plan.model_dump(),
            "retrieval_scope": payload["retrieval_scope"],
            "notes": notes,
            "follow_up_question": output.follow_up_question,
            "calculations": calculations,
            "validation": {
                "withheld_statements": len(withheld),
                "reasons": withheld,
                **(
                    {"unmatched_numeric_tokens": sorted(unmatched_numbers)}
                    if unmatched_numbers
                    else {}
                ),
            },
            "benchmark": payload.get("benchmark"),
            "provider": "openai",
            "model": calls[-1]["model"],
            "prompt_version": PROMPT_VERSION,
            "review_state": "ai_generated_citations_checked",
            "limitation": LIMITATION,
            "usage": usage,
            "estimated_cost_usd": str(cost),
            "cached": False,
            "model_called": True,
        }
        saved.payload, saved.status = answer, "completed"
        session.commit()
        LOG.info(
            "knowledge_research_completed answer_id=%s provider=openai model=%s",
            identifier,
            settings.openai_model,
        )
        return {**answer, "answer_id": str(identifier)}
    except ResearchError as exc:
        saved.status, saved.error_code = "failed", exc.code
        session.commit()
        LOG.warning(
            "knowledge_research_failed answer_id=%s code=%s", identifier, exc.code
        )
        raise
    except Exception:
        session.rollback()
        saved.status, saved.error_code = "failed", "unexpected_research_failure"
        session.commit()
        raise ResearchError("unexpected_research_failure") from None
