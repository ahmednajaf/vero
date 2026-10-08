"""PostgreSQL lexical search over ALL indexed pages, not a list of chosen metrics."""

import re
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, Select, case, cast, exists, func, select, tuple_
from sqlalchemy.orm import Session, aliased

from app.db.models import (
    Company,
    DocumentPage,
    DocumentTable,
    ExtractionRun,
    KnowledgeIndex,
    KnowledgeJob,
    KnowledgePassage,
    Report,
)
from app.discovery.crawler import SUPPLEMENT
from app.knowledge.contracts import Scope, SearchRequest
from app.knowledge.indexing import INDEX_VERSION

STOP = set(
    "a an the how what which who when where why does do did has have had is are was were of in on at for to and or compare between these those their about companies company reports report tell me please across all use uses using winning race best better worst leading leader leaders most least currently explain describe summarise summarize".split()
)
ALIASES = {
    "suppliers": ["supplier"],
    "decarbonisation": ["decarbonization"],
    "decarbonization": ["decarbonisation"],
    "remuneration": ["compensation"],
    "compensation": ["remuneration"],
    "biodiversity": ["ecosystem"],
    "water": ["withdrawal", "scarcity"],
}


def terms(query: str) -> list[str]:
    parts = re.findall(r'"([^"\n]{2,100})"|(\bnet[ -]+zero\b)|([\w-]+)', query.lower())
    phrases = [
        phrase or compound.replace("-", " ")
        for phrase, compound, _ in parts
        if phrase or compound
    ]
    found = [word for _, _, word in parts if word not in STOP and len(word) > 1][:30]
    return list(
        dict.fromkeys(
            [p.lower() for p in phrases]
            + found
            + [v for t in found for v in ALIASES.get(t, [])]
        )
    )[:30]


def lexical_rank(tokens: list[str]) -> tuple[Any, Any]:
    """Prefer coverage of query concepts over repetition of one generic word."""
    meaningful = [t for t in tokens if not t.isdigit()] or tokens
    tsquery = func.websearch_to_tsquery(
        "english", " OR ".join('"' + t + '"' for t in meaningful)
    )
    breadth = sum(
        cast(
            KnowledgePassage.search_vector.op("@@")(
                func.phraseto_tsquery("english", token)
            ),
            Integer,
        )
        * (0.25 if token.isdigit() else 1)
        for token in tokens
    )
    # Normalisation 32 bounds frequency relevance below 1, as a tie-breaker.
    score = breadth + func.ts_rank_cd(KnowledgePassage.search_vector, tsquery, 32)
    if any(
        re.search(r"\bfiscal\b|\bcalendar\b|reporting (period|year)", token)
        for token in tokens
    ):
        # Questions about the reporting calendar should surface definition sections,
        # not just data tables that repeat fiscal/calendar labels many times.
        score = score + case(
            (
                KnowledgePassage.content.op("~*")(
                    r"(^|\n)(Reporting year|Reporting period|About this report|Basis (of|for) preparation)(\n|$)"
                ),
                2,
            ),
            else_=0,
        )
    return tsquery, score


def company_scope(scope: Scope) -> list[Any]:
    members = select(KnowledgeJob.company_id).union(
        select(Report.company_id).join(
            KnowledgeIndex, KnowledgeIndex.report_id == Report.id
        )
    )
    result: list[Any] = [Company.active.is_(True), Company.id.in_(members)]
    if scope.company_ids:
        result.append(Company.id.in_(scope.company_ids))
    if scope.sector:
        result.append(Company.sector == scope.sector)
    if scope.country:
        result.append(Company.country == scope.country)
    if scope.report_ids:
        result.append(
            Company.id.in_(
                select(Report.company_id).where(Report.id.in_(scope.report_ids))
            )
        )
    return result


def report_scope(scope: Scope) -> list[Any]:
    result: list[Any] = []
    if scope.report_ids:
        result.append(Report.id.in_(scope.report_ids))
    if scope.report_year:
        # Deliberately a report label, never treated as the observation year.
        result.append(
            func.coalesce(Report.reporting_year, Report.detected_year)
            == scope.report_year
        )
    return result


def fresh() -> list[Any]:
    newer = aliased(ExtractionRun)
    return [
        Report.status == "downloaded",
        Report.source_policy == "official",
        Report.content_sha256 == KnowledgeIndex.report_sha256,
        Report.source_url == KnowledgeIndex.source_url,
        KnowledgeIndex.version == INDEX_VERSION,
        ExtractionRun.status == "succeeded",
        ExtractionRun.input_sha256 == Report.content_sha256,
        ~exists(
            select(newer.id).where(
                newer.report_id == Report.id,
                newer.stage == "parsing",
                (newer.created_at > ExtractionRun.created_at)
                | (
                    (newer.created_at == ExtractionRun.created_at)
                    & (newer.id > ExtractionRun.id)
                ),
            )
        ),
    ]


def base(scope: Scope) -> Select[Any]:
    return (
        select(KnowledgePassage, DocumentPage, Report, Company, KnowledgeIndex)
        .join(KnowledgeIndex, KnowledgeIndex.id == KnowledgePassage.index_id)
        .join(Report, Report.id == KnowledgeIndex.report_id)
        .join(Company, Company.id == Report.company_id)
        .join(DocumentPage, DocumentPage.id == KnowledgePassage.page_id)
        .join(ExtractionRun, ExtractionRun.id == KnowledgeIndex.parse_run_id)
        .where(*fresh(), *company_scope(scope), *report_scope(scope))
    )


def hit(row: Any, score: float = 0) -> dict[str, Any]:
    passage, page, report, company, index = row[:5]
    return {
        "evidence_id": str(passage.id),
        "company_id": str(company.id),
        "company": company.company_name,
        "sector": company.sector,
        "country": company.country,
        "report_id": str(report.id),
        "report": report.title,
        "document_role": "supporting_document"
        if SUPPLEMENT.search(report.title + " " + report.source_url)
        else "primary_report_candidate",
        "reporting_year": report.reporting_year,
        "detected_year": report.detected_year,
        "requested_year": report.requested_year,
        "source_url": report.source_url,
        "report_sha256": report.content_sha256,
        "page": page.page_number,
        "printed_page_label": page.printed_page_label,
        "page_url": f"/api/reports/{report.id}/file#page={page.page_number}",
        "text": passage.content,
        "text_sha256": passage.content_sha256,
        "kind": passage.kind,
        "locator": passage.locator,
        "headings": page.headings,
        "index_fingerprint": index.fingerprint,
        "score": round(float(score), 6),
        "review_state": "unreviewed_source_text",
        "page_status": page.status,
    }


def indexed_sources(scope: Scope) -> Select[Any]:
    """One row per current nonempty index, without a passage × large-JSON sort."""
    return (
        select(
            Report.id,
            Company.id.label("company_id"),
            KnowledgeIndex.quality,
            Report.title,
            Report.source_url,
        )
        .select_from(KnowledgeIndex)
        .join(Report, Report.id == KnowledgeIndex.report_id)
        .join(Company, Company.id == Report.company_id)
        .join(ExtractionRun, ExtractionRun.id == KnowledgeIndex.parse_run_id)
        .where(
            *fresh(),
            *company_scope(scope),
            *report_scope(scope),
            exists(
                select(KnowledgePassage.id).where(
                    KnowledgePassage.index_id == KnowledgeIndex.id
                )
            ),
        )
    )


def coverage(session: Session, scope: Scope) -> dict[str, Any]:
    companies = (
        session.scalar(
            select(func.count()).select_from(Company).where(*company_scope(scope))
        )
        or 0
    )
    reports = (
        select(Report.id)
        .join(Company)
        .where(
            *company_scope(scope),
            *report_scope(scope),
            Report.id.in_(library_report_ids(session)),
            Report.status == "downloaded",
            Report.source_policy == "official",
        )
    )
    records = session.execute(indexed_sources(scope)).all()
    return {
        "companies_in_scope": companies,
        "official_reports_downloaded": session.scalar(
            select(func.count()).select_from(reports.subquery())
        )
        or 0,
        "reports_indexed": len(records),
        "supporting_documents_indexed": sum(
            bool(SUPPLEMENT.search(r.title + " " + r.source_url)) for r in records
        ),
        "primary_report_candidates_indexed": sum(
            not SUPPLEMENT.search(r.title + " " + r.source_url) for r in records
        ),
        "companies_with_indexed_reports": len({r.company_id for r in records}),
        "companies_with_primary_report_candidates": len(
            {
                r.company_id
                for r in records
                if not SUPPLEMENT.search(r.title + " " + r.source_url)
            }
        ),
        "pages_indexed": sum(int(r.quality.get("pages_total", 0)) for r in records),
        "reports_with_text_gaps": sum(
            r.quality.get("coverage") != "complete_extracted_text" for r in records
        ),
        "meaning": "Index coverage, not metric validation or corporate disclosure completeness.",
    }


def reports(
    session: Session, scope: Scope, *, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    query = (
        select(Report, Company.company_name, KnowledgeIndex)
        .join(Company)
        .outerjoin(KnowledgeIndex, KnowledgeIndex.report_id == Report.id)
        .where(
            *company_scope(scope),
            *report_scope(scope),
            Report.id.in_(library_report_ids(session)),
            Report.status == "downloaded",
            Report.source_policy == "official",
        )
    )
    current = set(session.scalars(indexed_sources(scope).with_only_columns(Report.id)))
    rows = session.execute(
        query.order_by(Company.company_name, Report.created_at.desc(), Report.id)
        .offset(offset)
        .limit(limit)
    )
    return {
        "coverage": coverage(session, scope),
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": str(r.id),
                "company_id": str(r.company_id),
                "company": name,
                "title": r.title,
                "document_role": "supporting_document"
                if SUPPLEMENT.search(r.title + " " + r.source_url)
                else "primary_report_candidate",
                "reporting_year": r.reporting_year,
                "requested_year": r.requested_year,
                "detected_year": r.detected_year,
                "source_url": r.source_url,
                "retrieved_at": r.retrieved_at.isoformat() if r.retrieved_at else None,
                "sha256": r.content_sha256,
                "file_url": f"/api/reports/{r.id}/file",
                "parse_status": r.parse_status,
                "knowledge_status": "indexed"
                if r.id in current
                else "stale"
                if index
                else "not_indexed",
                "quality": index.quality if index else None,
            }
            for r, name, index in rows
        ],
    }


def library_report_ids(session: Session) -> list[UUID]:
    """Only explicitly indexed sources or this collection's actual job reports.

    A new job for Apple must not silently surface every historic Apple record.
    Failed downloads remain in job diagnostics, not the downloaded-source list.
    """
    identifiers = set(session.scalars(select(KnowledgeIndex.report_id)))
    for outcome in session.scalars(select(KnowledgeJob.outcome)):
        values = [outcome.get("report_id")]
        report_outcomes = outcome.get("reports", [])
        if isinstance(report_outcomes, list):
            values.extend(
                r.get("report_id") for r in report_outcomes if isinstance(r, dict)
            )
        for value in values:
            if isinstance(value, str):
                identifiers.add(UUID(value))
    return list(identifiers)


def search(session: Session, request: SearchRequest) -> dict[str, Any]:
    tokens = terms(request.query)
    common = {
        "query": request.query,
        "terms": tokens,
        "scope": request.model_dump(mode="json", exclude={"query", "limit", "offset"}),
        "coverage": coverage(session, request),
        "offset": request.offset,
        "limit": request.limit,
        "retrieval": "postgresql_english_term_coverage_v2",
    }
    if not tokens:
        return {**common, "total": 0, "items": []}
    # Tokens originate from a restrictive tokenizer; still passed as bound values.
    tsquery, rank = lexical_rank(tokens)
    query = base(request).where(KnowledgePassage.search_vector.op("@@")(tsquery))
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.add_columns(rank)
        .order_by(rank.desc(), Report.id, KnowledgePassage.ordinal)
        .offset(request.offset)
        .limit(request.limit)
    ).all()
    return {**common, "total": total, "items": [hit(r, r[-1]) for r in rows]}


def balanced_candidates(
    session: Session, request: SearchRequest, *, per_company: int = 8
) -> dict[str, Any]:
    """Rank WITHIN each company before limiting; global top-k starves small reports.

    One candidate per page/kind keeps both table and prose evidence eligible without
    allowing hundreds of table fragments on one page to consume the context.
    Only IDs and ranks participate in window sorts, never large text/JSON columns.
    """
    tokens = terms(request.query)
    if not tokens:
        return {"total": 0, "items": [], "company_counts": {}}
    tsquery, rank = lexical_rank(tokens)
    order = (rank.desc(), Report.id, KnowledgePassage.ordinal)
    matched = (
        base(request)
        .where(KnowledgePassage.search_vector.op("@@")(tsquery))
        .with_only_columns(
            KnowledgePassage.id.label("passage_id"),
            Company.id.label("company_id"),
            Report.id.label("report_id"),
            KnowledgePassage.ordinal,
            rank.label("score"),
            func.count().over(partition_by=Company.id).label("company_count"),
            func.row_number()
            .over(
                partition_by=(Company.id, DocumentPage.id, KnowledgePassage.kind),
                order_by=order,
            )
            .label("page_rank"),
        )
        .subquery()
    )
    ranked = (
        select(
            matched,
            func.row_number()
            .over(
                partition_by=matched.c.company_id,
                order_by=(
                    matched.c.score.desc(),
                    matched.c.report_id,
                    matched.c.ordinal,
                ),
            )
            .label("company_rank"),
        )
        .where(matched.c.page_rank == 1)
        .subquery()
    )
    rows = session.execute(
        base(request)
        .join(ranked, ranked.c.passage_id == KnowledgePassage.id)
        .where(ranked.c.company_rank <= per_company)
        .add_columns(ranked.c.score, ranked.c.company_count)
        .order_by(Company.company_name, Company.id, ranked.c.company_rank)
    ).all()
    counts = {str(row[3].id): int(row[-1]) for row in rows}
    return {
        "total": sum(counts.values()),
        "company_counts": counts,
        "items": [hit(row, row[-2]) for row in rows],
    }


def adjacent_text_candidates(
    session: Session, scope: Scope, sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """One contiguous same-page window per lead passage; never cross a PDF page.

    Prefer preceding context (definitions/table headings), otherwise following.
    Retain distinct evidence IDs and original hashes, not a fabricated merged chunk.
    """
    keys = {(UUID(s["report_id"]), s["page"]) for s in sources if s["kind"] == "text"}
    if not keys:
        return []
    rows = session.execute(
        base(scope).where(
            tuple_(Report.id, DocumentPage.page_number).in_(keys),
            KnowledgePassage.kind == "text",
        )
    ).all()
    pages: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        item = hit(row)
        pages.setdefault((item["report_id"], item["page"]), []).append(item)
    result = []
    for source in sources:
        if source["kind"] != "text":
            continue
        neighbours = [
            item
            for item in pages.get((source["report_id"], source["page"]), [])
            if item["evidence_id"] != source["evidence_id"]
            and (
                item["locator"].get("end") == source["locator"].get("start")
                or item["locator"].get("start") == source["locator"].get("end")
            )
        ]
        if neighbours:
            result.append(
                {
                    **min(neighbours, key=lambda x: x["locator"].get("start", 0)),
                    "retrieval_role": "adjacent_same_page_context",
                }
            )
    return result


def evidence(session: Session, identifier: UUID) -> dict[str, Any] | None:
    row = session.execute(
        base(Scope()).where(KnowledgePassage.id == identifier)
    ).first()
    if not row:
        return None
    result = hit(row)
    page = row[1]
    result["page_text"] = page.raw_text
    result["tables"] = [
        {
            "id": str(t.id),
            "cells": t.cells,
            "header_metadata": t.header_metadata,
            "bbox": t.bbox,
            "validation_state": t.validation_state,
        }
        for t in session.scalars(
            select(DocumentTable)
            .where(DocumentTable.document_page_id == page.id)
            .order_by(DocumentTable.table_index)
        )
    ]
    return result


def topic_coverage(session: Session, request: SearchRequest) -> dict[str, Any]:
    """Count literal retrieval matches across the scope, NEVER inferred disclosures."""
    tokens = terms(request.query)
    matched: dict[UUID, int] = {}
    if tokens:
        query = base(request).where(
            KnowledgePassage.search_vector.op("@@")(
                func.websearch_to_tsquery("english", " OR ".join(tokens))
            )
        )
        rows = session.execute(
            query.with_only_columns(
                Company.id, func.count(func.distinct(Report.id))
            ).group_by(Company.id)
        )
        matched = {identifier: count for identifier, count in rows}
    indexed_ids = set(
        session.scalars(indexed_sources(request).with_only_columns(Company.id))
    )
    companies = session.scalars(
        select(Company).where(*company_scope(request)).order_by(Company.company_name)
    )
    items = [
        {
            "company_id": str(c.id),
            "company": c.company_name,
            "matching_reports": matched.get(c.id, 0),
            "status": "matches_found"
            if c.id in matched
            else "not_found_in_index"
            if c.id in indexed_ids
            else "not_indexed",
        }
        for c in companies
    ]
    return {
        "query": request.query,
        "coverage": coverage(session, request),
        "items": items,
        "meaning": "Lexical search coverage only. A match does not establish disclosure; no match does not establish absence.",
    }
