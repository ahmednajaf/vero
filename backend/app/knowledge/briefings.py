"""Shared company/peer research workspace. No automatic calls on read or export."""

import csv
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Company, KnowledgeIndex, PeerBriefing
from app.knowledge.contracts import BRIEFING_PROMPT_PREFIX, AskRequest, Scope
from app.knowledge.provider import ResearchError, ResearchProvider
from app.knowledge.research import ask
from app.knowledge.search import company_scope, indexed_sources, reports

VERSION = "peer-workspace-v1"
TOPICS = {
    "emissions": (
        "Emissions & progress",
        "Compare reported Scope 1, Scope 2 location-based and market-based, Scope 3 totals, and changes against stated baselines. Keep units, years and boundaries attached; do not derive missing totals.",
    ),
    "energy": (
        "Energy",
        "Compare renewable electricity separately from renewable energy, with reported shares, measurement years and procurement approaches. Distinguish achieved results from goals.",
    ),
    "targets": (
        "Targets & transition",
        "Compare net-zero and interim targets, their dates, scopes, baselines and reported implementation. Explain concrete differences, not an overall winner.",
    ),
    "assurance": (
        "Assurance & governance",
        "Compare independent assurance provider, level and scope, and board oversight. Do not equate assurance of selected measures with assurance of an entire report.",
    ),
    "nature": (
        "Water & nature",
        "Compare water withdrawal versus consumption, biodiversity and waste programmes and reported outcomes. Keep denominators and operating boundaries visible.",
    ),
    "supply_chain": (
        "Supply chain",
        "Compare supplier emissions programmes, engagement and responsible sourcing, distinguishing activities, targets and measured results.",
    ),
}


class BriefingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary_company_id: UUID
    peer_ids: list[UUID] = Field(default_factory=list, max_length=4)
    topics: list[
        Literal["emissions", "energy", "targets", "assurance", "nature", "supply_chain"]
    ] = Field(
        default=["emissions", "energy", "targets", "assurance"],
        min_length=1,
        max_length=6,
    )
    focus: str = Field(default="", max_length=350)

    @model_validator(mode="after")
    def unique(self) -> "BriefingRequest":
        if (
            len(set(self.peer_ids)) != len(self.peer_ids)
            or self.primary_company_id in self.peer_ids
        ):
            raise ValueError("Choose distinct companies.")
        if len(set(self.topics)) != len(self.topics):
            raise ValueError("Choose distinct topics.")
        return self


def scope_for(row: PeerBriefing) -> Scope:
    return Scope(
        company_ids=row.definition["company_ids"],
        report_ids=row.definition["report_ids"],
    )


def signature(session: Session, scope: Scope) -> str:
    values = session.execute(
        indexed_sources(scope).with_only_columns(
            KnowledgeIndex.report_id, KnowledgeIndex.fingerprint
        )
    ).all()
    return hashlib.sha256(
        json.dumps(sorted((str(r), f) for r, f in values)).encode()
    ).hexdigest()


def create(session: Session, request: BriefingRequest) -> PeerBriefing:
    ids = [request.primary_company_id, *request.peer_ids]
    scope = Scope(company_ids=ids)
    companies = {
        c.id: c for c in session.scalars(select(Company).where(*company_scope(scope)))
    }
    if set(companies) != set(ids):
        raise ResearchError("briefing_company_unavailable")
    current = list(session.execute(indexed_sources(scope)))
    if not current:
        raise ResearchError("briefing_no_searchable_reports")
    report_ids = [r.id for r in current]
    scope.report_ids = report_ids
    primary = companies[request.primary_company_id]
    row = PeerBriefing(
        primary_company_id=primary.id,
        title=f"{primary.company_name} · {'Peer comparison' if request.peer_ids else 'Company analysis'}"[
            :240
        ],
        status="pending",
        source_signature=signature(session, scope),
        definition={
            "version": VERSION,
            "company_ids": [str(i) for i in ids],
            "report_ids": [str(i) for i in report_ids],
            "companies": [
                {
                    "id": str(i),
                    "company_name": companies[i].company_name,
                    "sector": companies[i].sector,
                    "country": companies[i].country,
                    "reports_indexed": sum(r.company_id == i for r in current),
                }
                for i in ids
            ],
            "reports": reports(session, scope, limit=100)["items"],
            "focus": request.focus,
        },
        sections=[
            {
                "id": k,
                "title": TOPICS[k][0],
                "status": "pending",
                "result": None,
                "error_code": None,
            }
            for k in request.topics
        ],
    )
    session.add(row)
    session.commit()
    return row


def snapshot(session: Session, row: PeerBriefing) -> dict[str, Any]:
    now = datetime.now(UTC)
    running = (
        row.status == "running"
        and row.lease_until is not None
        and row.lease_until > now
    )
    indexed = {
        str(r.company_id) for r in session.execute(indexed_sources(scope_for(row)))
    }
    latest_ids = {
        str(r.id)
        for r in session.execute(
            indexed_sources(Scope(company_ids=row.definition["company_ids"]))
        )
    }
    matrix, gaps = [], []
    total_claims = 0
    known_cost = 0.0
    for section in row.sections:
        result = section.get("result") or {}
        claims = result.get("claims", [])
        total_claims += len(claims)
        known_cost += (
            float(result.get("estimated_cost_usd") or 0)
            if not result.get("cached")
            else 0
        )
        citations = [c for claim in claims for c in claim["citations"]]
        supplied = {
            c["company_id"]
            for c in result.get("coverage", {}).get("companies", [])
            if c["status"] == "supplied"
        }
        cells = []
        for company in row.definition["companies"]:
            own = list(
                {
                    c["evidence_id"]: c
                    for c in citations
                    if c["company_id"] == company["id"]
                }.values()
            )
            state = (
                "evidence_found"
                if own
                else "report_unavailable"
                if company["id"] not in indexed
                else "pending"
                if not result
                else "passages_retrieved"
                if company["id"] in supplied
                else "not_identified"
            )
            cells.append({"company_id": company["id"], "status": state, "sources": own})
        peers = [c for c in cells[1:] if c["status"] == "evidence_found"]
        if result and cells[0]["status"] != "evidence_found" and peers:
            gaps.append(
                {
                    "topic": section["title"],
                    "topic_id": section["id"],
                    "peer_evidence_count": len(peers),
                    "peer_count": len(cells) - 1,
                    "primary_status": cells[0]["status"],
                    "sources": [c["sources"][0] for c in peers],
                    "meaning": "Peer evidence found; this company's position needs investigation. Not proof of a missing disclosure.",
                }
            )
        matrix.append(
            {"topic_id": section["id"], "topic": section["title"], "cells": cells}
        )
    return {
        "id": str(row.id),
        "title": row.title,
        "primary_company_id": str(row.primary_company_id),
        "status": row.status if row.status != "running" or running else "paused",
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "definition": row.definition,
        "sections": row.sections,
        "sources_current": row.source_signature == signature(session, scope_for(row)),
        "new_reports_available": len(latest_ids - set(row.definition["report_ids"])),
        "can_resume": not running
        and any(s["status"] != "completed" for s in row.sections),
        "completed_topics": sum(s["status"] == "completed" for s in row.sections),
        "findings_count": total_claims,
        "matrix": matrix,
        "review_opportunities": gaps,
        "estimated_cost_usd": round(known_cost, 6),
        "cost_note": "Known successful non-cached calls only; failed calls may also incur usage.",
    }


async def advance(
    session: Session,
    identifier: UUID,
    settings: Settings,
    provider: ResearchProvider | None = None,
) -> dict[str, Any]:
    row = session.scalar(
        select(PeerBriefing).where(PeerBriefing.id == identifier).with_for_update()
    )
    if row is None:
        raise ResearchError("briefing_not_found")
    now = datetime.now(UTC)
    if row.lease_until and row.lease_until > now:
        session.rollback()
        raise ResearchError("briefing_busy")
    if row.source_signature != signature(session, scope_for(row)):
        session.rollback()
        raise ResearchError("briefing_sources_changed")
    index = next(
        (i for i, s in enumerate(row.sections) if s["status"] != "completed"), None
    )
    if index is None:
        session.rollback()
        return snapshot(session, row)
    token = uuid4()
    row.lease_token, row.lease_until = (
        token,
        now + timedelta(seconds=2 * settings.openai_timeout_seconds + 120),
    )
    row.status = "running"
    sections = [dict(s) for s in row.sections]
    sections[index] = {**sections[index], "status": "running", "error_code": None}
    row.sections = sections
    session.commit()
    question = (
        BRIEFING_PROMPT_PREFIX
        + TOPICS[sections[index]["id"]][1]
        + " Give concise standalone findings with named companies and sources. Explain useful reported differences even when a ranking is not justified. "
        + "Do not claim a disclosure is absent because it was not retrieved. Each finding must make sense independently."
        + (
            f" Additional focus: {row.definition['focus']}"
            if row.definition.get("focus")
            else ""
        )
    )
    # Frozen report IDs prevent new acquisitions silently changing an unfinished result.
    request = AskRequest(**scope_for(row).model_dump(), question=question[:1200])
    error = None
    result = None
    try:
        result = await ask(session, request, settings, provider=provider)
    except ResearchError as exc:
        error = exc.code
    except Exception:
        session.rollback()
        error = "briefing_processing_failed"
    session.expire_all()
    row = session.scalar(
        select(PeerBriefing).where(PeerBriefing.id == identifier).with_for_update()
    )
    if row is None or row.lease_token != token:
        session.rollback()
        raise ResearchError("briefing_busy")
    sections = [dict(s) for s in row.sections]
    sections[index] = {
        **sections[index],
        "status": "failed" if error else "completed",
        "error_code": error,
        "result": result,
    }
    row.sections = sections
    row.lease_token, row.lease_until = None, None
    if error:
        row.status = "failed"
    elif any(s["status"] != "completed" for s in sections):
        row.status = "pending"
    else:
        row.status = (
            "ready"
            if all(s["result"]["status"] == "answered" for s in sections)
            else "partial"
        )
    session.commit()
    return snapshot(session, row)


def recent(session: Session, company_id: UUID | None = None) -> dict[str, Any]:
    query = select(PeerBriefing).order_by(PeerBriefing.created_at.desc())
    if company_id:
        query = query.where(
            PeerBriefing.definition["company_ids"].contains([str(company_id)])
        )
    items = []
    for row in session.scalars(query.limit(50)):
        items.append(
            {
                "id": str(row.id),
                "title": row.title,
                "status": row.status,
                "created_at": row.created_at.isoformat(),
                "companies": row.definition["companies"],
                "topics": len(row.sections),
                "completed_topics": sum(
                    s["status"] == "completed" for s in row.sections
                ),
                "findings": sum(
                    len((s.get("result") or {}).get("claims", [])) for s in row.sections
                ),
            }
        )
    return {"items": items}


def export_csv(payload: dict[str, Any]) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        [
            "Topic",
            "Topic status",
            "Finding",
            "Company",
            "Report",
            "Document year",
            "Physical page",
            "Excerpt",
            "Source URL",
            "Document SHA256",
            "Model",
            "Answer ID",
            "Source current",
            "Limitations",
        ]
    )

    def safe(value: Any) -> str:
        cell = str(value if value is not None else "")
        return "'" + cell if cell.lstrip().startswith(("=", "+", "-", "@")) else cell

    for section in payload["sections"]:
        result = section.get("result") or {}
        claims = result.get("claims") or [
            {"text": "No supported finding established", "citations": [{}]}
        ]
        for claim in claims:
            for source in claim["citations"]:
                writer.writerow(
                    [
                        safe(v)
                        for v in [
                            section["title"],
                            section["status"],
                            claim["text"],
                            source.get("company"),
                            source.get("report"),
                            source.get("reporting_year") or source.get("detected_year"),
                            source.get("page"),
                            source.get("quote"),
                            source.get("source_url"),
                            source.get("report_sha256"),
                            result.get("model"),
                            result.get("answer_id"),
                            payload["sources_current"],
                            " ".join(result.get("notes", []))
                            or section.get("error_code"),
                        ]
                    ]
                )
    return "\ufeff" + stream.getvalue()


def export_html(payload: dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        return escape(str(value))

    parts = [
        f"<!doctype html><html lang='en'><meta charset='utf-8'><title>{esc(payload['title'])}</title><style>body{{font:15px/1.7 system-ui;color:#19202c;max-width:960px;margin:48px auto;padding:24px}}h1{{font-size:32px}}h2{{margin-top:36px}}article{{border-bottom:1px solid #ddd;padding:16px 0}}small{{color:#536074}}blockquote{{border-left:3px solid #7d83bf;padding-left:16px}}@media print{{button{{display:none}}article{{break-inside:avoid}}body{{margin:0}}}}</style><b>VERO / COMPANY INTELLIGENCE</b><h1>{esc(payload['title'])}</h1><p>{esc(payload['created_at'])} · {esc(payload['status'])}</p><p>AI-assisted report analysis, not an ESG rating. Reported facts retain their original scope and period. Sources {'current' if payload['sources_current'] else 'changed since this analysis; historical result'}.</p>"
    ]
    parts.append(
        "<p>Companies: "
        + esc(", ".join(c["company_name"] for c in payload["definition"]["companies"]))
        + "</p>"
    )
    for section in payload["sections"]:
        result = section.get("result") or {}
        parts.append(
            f"<h2>{esc(section['title'])}</h2><small>{esc(section['status'])} · {esc(result.get('model', ''))}</small>"
        )
        if not result.get("claims"):
            parts.append(
                "<p>No supported finding established. "
                + esc(section.get("error_code") or "")
                + "</p>"
            )
        for claim in result.get("claims", []):
            parts.append(f"<article><p>{esc(claim['text'])}</p>")
            for source in claim["citations"]:
                url = (
                    source["source_url"]
                    if urlparse(source["source_url"]).scheme in {"http", "https"}
                    else "#"
                )
                parts.append(
                    f"<small>{esc(source['company'])} · {esc(source['report'])} · physical page {source['page']}</small><blockquote>{esc(source['quote'])}</blockquote><a href='{esc(url)}'>Official report</a><br><small>SHA-256: {esc(source['report_sha256'])}</small>"
                )
            parts.append("</article>")
        parts.extend(f"<p><small>{esc(n)}</small></p>" for n in result.get("notes", []))
    parts.append(
        "<h2>Evidence gaps to investigate</h2><p>Not identified is not proof of non-disclosure. Peer counts below describe this saved analysis, not exhaustive reporting coverage.</p>"
    )
    for gap in payload["review_opportunities"]:
        parts.append(
            f"<p>{esc(gap['topic'])}: evidence cited for {gap['peer_evidence_count']} / {gap['peer_count']} selected peers; primary company: {esc(gap['primary_status'])}.</p>"
        )
    parts.append(
        "<footer>Quotes and numbers are mechanically checked; interpretation may still require review. Document year is not necessarily the measurement year. Use your browser’s Print → Save as PDF to share this briefing.</footer></html>"
    )
    return "".join(parts)
