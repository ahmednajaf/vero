"""Company intelligence, peer workspaces and portable evidence exports."""

from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import PeerBriefing
from app.db.session import get_session
from app.knowledge import briefings
from app.knowledge.provider import ResearchError
from app.knowledge.explanation import ExplainRequest, explain

router = APIRouter(prefix="/api/knowledge/briefings", tags=["peer intelligence"])


def get_row(session: Session, identifier: UUID) -> PeerBriefing:
    row = session.get(PeerBriefing, identifier)
    if row is None:
        raise HTTPException(404, "Saved analysis not found.")
    return row


@router.get("")
def list_briefings(
    company_id: UUID | None = None, session: Session = Depends(get_session)
) -> dict[str, Any]:
    return briefings.recent(session, company_id)


@router.post("", status_code=201)
def create_briefing(
    body: briefings.BriefingRequest, session: Session = Depends(get_session)
) -> dict[str, Any]:
    try:
        return briefings.snapshot(session, briefings.create(session, body))
    except ResearchError as exc:
        raise HTTPException(422, {"code": exc.code}) from None


@router.get("/{identifier}")
def detail(identifier: UUID, session: Session = Depends(get_session)) -> dict[str, Any]:
    return briefings.snapshot(session, get_row(session, identifier))


@router.post("/{identifier}/advance")
async def advance(
    identifier: UUID, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    get_row(session, identifier)
    try:
        return await briefings.advance(
            session, identifier, cast(Settings, request.app.state.settings)
        )
    except ResearchError as exc:
        raise HTTPException(409, {"code": exc.code}) from None


@router.post("/{identifier}/explain")
async def explain_analysis(identifier: UUID, body: ExplainRequest, request: Request,
                           session: Session = Depends(get_session)) -> dict[str, Any]:
    payload = briefings.snapshot(session, get_row(session, identifier))
    try:
        return await explain(request.app.state.database_engine, payload, body, request.app.state.settings)
    except ResearchError as exc:
        raise HTTPException(409, {"code": exc.code}) from None


@router.get("/{identifier}/export")
def export(
    identifier: UUID,
    request: Request,
    format: Literal["html", "pdf", "xlsx", "csv", "json"] = "pdf",
    session: Session = Depends(get_session),
) -> Response:
    import json

    payload = briefings.snapshot(session, get_row(session, identifier))
    if format in {"html", "pdf"}:
        from app.knowledge import report_exports
        content, media = (report_exports.pdf(payload), "application/pdf") if format == "pdf" else (report_exports.html(payload), "text/html")
    elif format == "xlsx":
        from app.knowledge.workbook_export import export_workbook
        try:
            content = export_workbook(payload, request.app.state.settings)
        except RuntimeError as exc:
            raise HTTPException(503, {"code": str(exc)}) from None
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif format == "csv":
        content, media = briefings.export_csv(payload), "text/csv"
    else:
        content, media = json.dumps(payload, indent=2), "application/json"
    return Response(
        content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="vero-analysis-{identifier}.{format}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
        },
    )
