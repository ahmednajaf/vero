"""One Vero API for document knowledge and grounded research; UI-independent."""

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import KnowledgeAnswer, KnowledgeJob, ReportCollection
from app.db.session import get_session
from app.knowledge.contracts import AskRequest, Scope, SearchRequest
from app.knowledge.provider import ResearchError, configured
from app.knowledge.inspection import inspect_source
from app.knowledge.research import ask, preview
from app.knowledge.search import coverage, evidence, reports, search, topic_coverage
from app.knowledge.workspace import company_directory, recent_answers
from app.knowledge.budget import usage_summary

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/companies")
def directory(session: Session = Depends(get_session)) -> dict[str, Any]:
    return company_directory(session)


@router.get("/answers")
def history(session: Session = Depends(get_session)) -> dict[str, Any]:
    return recent_answers(session)


@router.get("/collections")
def collections(session: Session = Depends(get_session)) -> dict[str, Any]:
    return {
        "items": [
            {
                "run_id": str(r.id),
                "year": r.year,
                "status": r.status,
                "companies": len(r.company_ids),
                "processed": len(r.results),
                "started_at": r.started_at,
                "finished_at": r.finished_at,
            }
            for r in session.scalars(
                select(ReportCollection)
                .order_by(ReportCollection.created_at.desc())
                .limit(20)
            )
        ]
    }


@router.get("/collections/{run_id}")
def collection_details(
    run_id: UUID, session: Session = Depends(get_session)
) -> dict[str, Any]:
    from app.knowledge.collection import snapshot

    try:
        return snapshot(session.get_bind(), run_id)
    except ValueError:
        raise HTTPException(404, "Collection not found.") from None


@router.get("/reports")
def library(
    company_id: UUID | None = None,
    year: int | None = Query(None, ge=2000, le=2100),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return reports(
        session,
        Scope(company_ids=[company_id] if company_id else [], report_year=year),
        limit=limit,
        offset=offset,
    )


@router.get("/status")
def status(request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    settings = cast(Settings, request.app.state.settings)
    return {
        **coverage(session, Scope()),
        "ingestion_jobs": {
            state: count
            for state, count in session.execute(
                select(KnowledgeJob.status, func.count()).group_by(KnowledgeJob.status)
            )
        },
        "research": {
            "provider": "openai",
            "model": settings.openai_model or None,
            "enabled": settings.knowledge_ai_enabled,
            "configuration_error": configured(settings),
            "connectivity_tested": False,
            "monthly_budget_usd": settings.knowledge_monthly_budget_usd,
            "daily_app_token_limit": settings.openai_daily_token_limit,
            "usage": usage_summary(session, settings),
            "cost_basis": "Conservative list-price estimate, not actual OpenAI billing or remaining organization allowance",
        },
    }


@router.post("/search")
def search_documents(
    body: SearchRequest, session: Session = Depends(get_session)
) -> dict[str, Any]:
    return search(session, body)


@router.get("/reports/{report_id}/inspection")
def inspect_report(
    report_id: UUID, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    result = inspect_source(
        session, report_id, cast(Settings, request.app.state.settings), verify_file=True
    )
    if result is None:
        raise HTTPException(404, "Current indexed official report not found.")
    return result


@router.post("/preview")
def preview_research(
    body: AskRequest, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    try:
        return preview(session, body, cast(Settings, request.app.state.settings))
    except ResearchError as exc:
        raise HTTPException(422, {"code": exc.code}) from None


@router.post("/coverage")
def coverage_by_company(
    body: SearchRequest, session: Session = Depends(get_session)
) -> dict[str, Any]:
    return topic_coverage(session, body)


@router.get("/evidence/{evidence_id}")
def source(
    evidence_id: UUID, session: Session = Depends(get_session)
) -> dict[str, Any]:
    found = evidence(session, evidence_id)
    if found is None:
        raise HTTPException(404, "Evidence unavailable or its source index is stale.")
    return found


@router.post("/ask")
async def research(
    body: AskRequest, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    try:
        return await ask(session, body, cast(Settings, request.app.state.settings))
    except ResearchError as exc:
        code = 503
        if exc.code == "monthly_budget_exceeded":
            code = 429
        elif "population" in exc.code or "conversation" in exc.code:
            code = 422
        elif exc.code == "research_busy_or_interrupted":
            code = 409
        elif exc.code in {
            "unsupported_citation",
            "unsupported_number",
            "answer_status_conflict",
        }:
            code = 502
        raise HTTPException(
            code,
            {
                "code": exc.code,
                "message": "No uncited or fallback answer substituted. Source search remains available.",
            },
        ) from None


@router.get("/answers/{answer_id}")
def answer_status(
    answer_id: UUID, session: Session = Depends(get_session)
) -> dict[str, Any]:
    saved = session.get(KnowledgeAnswer, answer_id)
    if not saved:
        raise HTTPException(404, "Research answer not found.")
    # Historical provenance remains inspectable, but must not masquerade as fresh.
    claims = cast(list[dict[str, Any]], saved.payload.get("claims", []))
    identifiers = {c["evidence_id"] for claim in claims for c in claim["citations"]}
    current = all(evidence(session, UUID(i)) is not None for i in identifiers)
    return {
        "answer_id": str(saved.id),
        "question": saved.question,
        "status": saved.status,
        "error_code": saved.error_code,
        "sources_current": current,
        "historical": True,
        "result": saved.payload,
        "reserved_usd": str(saved.reserved_usd),
        "estimated_cost_usd": str(saved.charged_usd)
        if saved.charged_usd is not None
        else None,
    }
