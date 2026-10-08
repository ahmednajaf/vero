"""Read models for the connected company library and saved research workspace."""

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    KnowledgeAnswer,
    KnowledgeJob,
    Report,
    ReportDiscoveryRun,
)
from app.knowledge.contracts import BRIEFING_PROMPT_PREFIX, Scope
from app.knowledge.search import company_scope, indexed_sources, library_report_ids


def company_directory(session: Session) -> dict[str, Any]:
    scope = Scope()
    indexed: dict[Any, list[Any]] = defaultdict(list)
    for row in session.execute(indexed_sources(scope)):
        indexed[row.company_id].append(row)
    downloaded = {
        company_id: count
        for company_id, count in session.execute(
            select(Report.company_id, func.count())
            .where(
                Report.id.in_(library_report_ids(session)),
                Report.status == "downloaded",
                Report.source_policy == "official",
            )
            .group_by(Report.company_id)
        ).all()
    }
    jobs = {
        j.company_id: j
        for j in session.scalars(select(KnowledgeJob).order_by(KnowledgeJob.year))
    }
    items = []
    discovery = {
        r.company_id: r
        for r in session.scalars(
            select(ReportDiscoveryRun)
            .distinct(ReportDiscoveryRun.company_id)
            .order_by(
                ReportDiscoveryRun.company_id, ReportDiscoveryRun.created_at.desc()
            )
        )
    }
    for company in session.scalars(
        select(Company).where(*company_scope(scope)).order_by(Company.company_name)
    ):
        count = downloaded.get(company.id, 0)
        current = indexed[company.id]
        job = jobs.get(company.id)
        items.append(
            {
                "id": str(company.id),
                "company_name": company.company_name,
                "ticker": company.ticker,
                "sector": company.sector,
                "industry": company.industry,
                "country": company.country,
                "region": company.region,
                "official_domain": company.official_domain,
                "exchange": company.exchange,
                "reports_downloaded": count,
                "reports_indexed": len(current),
                "pages_indexed": sum(
                    int(r.quality.get("pages_total", 0)) for r in current
                ),
                "text_gaps": any(
                    r.quality.get("coverage") != "complete_extracted_text"
                    for r in current
                ),
                "availability": "searchable"
                if current
                else "downloaded"
                if count
                else "not_collected",
                "collection_status": job.status if job else "not_attempted",
                "collection_reason": discovery[company.id].selection_reason
                if company.id in discovery
                else (
                    str(job.outcome.get("reason"))
                    if job and job.outcome.get("reason")
                    else None
                ),
            }
        )
    return {"items": items, "total": len(items)}


def recent_answers(session: Session) -> dict[str, Any]:
    return {
        "items": [
            {
                "answer_id": str(a.id),
                "question": a.question,
                "status": a.status,
                "created_at": a.created_at.isoformat(),
                "model": a.model,
                "error_code": a.error_code,
                "request_scope": a.payload.get("request_scope", {}),
                "parent_answer_id": a.payload.get("parent_answer_id"),
            }
            for a in session.scalars(
                select(KnowledgeAnswer)
                .where(
                    KnowledgeAnswer.status == "completed",
                    func.coalesce(KnowledgeAnswer.payload["task_type"].astext, "")
                    != "metric_extraction",
                    ~KnowledgeAnswer.question.startswith(BRIEFING_PROMPT_PREFIX),
                )
                .order_by(KnowledgeAnswer.created_at.desc())
                .limit(30)
            )
        ]
    }
