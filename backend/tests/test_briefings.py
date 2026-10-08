# ruff: noqa: F811 -- imported pytest corpus fixture is intentionally injected by name.
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KnowledgeIndex, KnowledgeJob, Company
from app.knowledge.briefings import (
    BriefingRequest,
    advance,
    create,
    export_csv,
    export_html,
    recent,
    snapshot,
)
from app.knowledge.provider import ResearchError
from test_knowledge import corpus, MockProvider, ai_settings  # noqa: F401


def request(ids, **kwargs):
    return BriefingRequest(
        primary_company_id=ids[0][0],
        peer_ids=[ids[1][0]],
        topics=["supply_chain", "nature"],
        **kwargs,
    )


def test_duplicate_companies_and_topics_are_rejected():
    identifier = uuid4()
    with pytest.raises(ValidationError):
        BriefingRequest(primary_company_id=identifier, peer_ids=[identifier])
    with pytest.raises(ValidationError):
        BriefingRequest(primary_company_id=identifier, topics=["energy", "energy"])


def test_create_is_free_freezes_reports_and_resume_does_not_repeat(db_engine, corpus):
    _, ids = corpus
    provider = MockProvider()
    with Session(db_engine) as session:
        row = create(session, request(ids))
        assert sorted(row.definition["report_ids"]) == sorted(
            str(r.report_id) for r in session.scalars(select(KnowledgeIndex)).all()
        )
        assert snapshot(session, row)["completed_topics"] == 0 and provider.calls == 0
        first = asyncio.run(advance(session, row.id, ai_settings(), provider))
        assert first["completed_topics"] == 1 and first["can_resume"]
        assert first["matrix"][0]["cells"][0]["status"] == "evidence_found"
        second = asyncio.run(advance(session, row.id, ai_settings(), provider))
        assert second["completed_topics"] == 2 and not second["can_resume"]
        third = asyncio.run(advance(session, row.id, ai_settings(), provider))
        assert third["findings_count"] == 2 and provider.calls == 2
        assert recent(session, ids[1][0])["items"][0]["id"] == str(row.id)
        assert recent(session, uuid4())["items"] == []


def test_partial_failure_retains_previous_topic_and_safe_retry(db_engine, corpus):
    _, ids = corpus
    with Session(db_engine) as session:
        row = create(session, request(ids))
        asyncio.run(advance(session, row.id, ai_settings(), MockProvider()))
        failed = asyncio.run(
            advance(session, row.id, ai_settings(), MockProvider(fail=True))
        )
        assert failed["status"] == "failed" and failed["completed_topics"] == 1
        assert failed["sections"][1]["error_code"] == "openai_timeout"
        provider = MockProvider()
        result = asyncio.run(advance(session, row.id, ai_settings(), provider))
        assert result["completed_topics"] == 2 and provider.calls == 1


def test_busy_lease_and_changed_source_prevent_duplicate_or_stale_work(
    db_engine, corpus
):
    _, ids = corpus
    with Session(db_engine) as session:
        row = create(session, request(ids))
        row.status = "running"
        row.lease_until = datetime.now(UTC) + timedelta(minutes=2)
        session.commit()
        with pytest.raises(ResearchError, match="briefing_busy"):
            asyncio.run(advance(session, row.id, ai_settings(), MockProvider()))
        row.lease_until = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
        assert snapshot(session, row)["status"] == "paused"
        idx = session.scalar(select(KnowledgeIndex).limit(1))
        idx.fingerprint = "b" * 64
        session.commit()
        assert not snapshot(session, row)["sources_current"]
        with pytest.raises(ResearchError, match="briefing_sources_changed"):
            asyncio.run(advance(session, row.id, ai_settings(), MockProvider()))


def test_missing_company_report_is_not_zero_or_non_disclosure(db_engine, corpus):
    _, ids = corpus
    with Session(db_engine) as session:
        company = Company(
            company_name="Missing report fixture",
            ticker="MISSING",
            exchange="TEST",
            country="GB",
            region="Test",
            sector="Industrials",
            industry="Test",
            official_domain="example.com",
            reporting_year=2025,
        )
        session.add(company)
        session.flush()
        session.add(
            KnowledgeJob(company_id=company.id, year=2025, status="unavailable")
        )
        session.commit()
        row = create(
            session,
            BriefingRequest(
                primary_company_id=company.id,
                peer_ids=[ids[0][0]],
                topics=["supply_chain"],
            ),
        )
        result = asyncio.run(advance(session, row.id, ai_settings(), MockProvider()))
        assert result["matrix"][0]["cells"][0]["status"] == "report_unavailable"
        assert result["review_opportunities"][0]["peer_evidence_count"] == 1
        assert "Not proof" in result["review_opportunities"][0]["meaning"]


def test_newly_indexed_report_does_not_silently_change_saved_scope(db_engine, corpus):
    _, ids = corpus
    with Session(db_engine) as session:
        index = session.scalar(select(KnowledgeIndex).limit(1))
        original_hash = index.report_sha256
        index.report_sha256 = "f" * 64  # Simulate a report not yet freshly indexed.
        session.commit()
        row = create(session, request(ids))
        frozen_ids = list(row.definition["report_ids"])
        assert len(frozen_ids) == 1
        assert snapshot(session, row)["new_reports_available"] == 0
        index.report_sha256 = original_hash
        session.commit()
        state = snapshot(session, row)
        assert state["new_reports_available"] == 1
        assert state["sources_current"]
        assert state["definition"]["report_ids"] == frozen_ids


def test_portable_exports_preserve_provenance_and_escape_untrusted_text(
    db_engine, corpus
):
    _, ids = corpus
    with Session(db_engine) as session:
        row = create(session, request(ids))
        result = asyncio.run(advance(session, row.id, ai_settings(), MockProvider()))
        result["title"] = "<script>alert('fixture')</script>"
        result["sections"][0]["result"]["claims"][0]["text"] = (
            "=malicious spreadsheet formula"
        )
        html = export_html(result)
        assert "<script>" not in html and "&lt;script&gt;" in html
        assert "We train suppliers annually." in html and "physical page 2" in html
        csv = export_csv(result)
        assert "'=malicious" in csv and "Document SHA256" in csv
        assert "fixture-model" in csv


def test_api_save_read_and_exports_make_no_inference(api_client, corpus):
    _, ids = corpus
    created = api_client.post(
        "/api/knowledge/briefings", json=request(ids).model_dump(mode="json")
    )
    assert created.status_code == 201
    identifier = created.json()["id"]
    assert (
        api_client.get("/api/knowledge/briefings").json()["items"][0]["id"]
        == identifier
    )
    assert (
        api_client.get(f"/api/knowledge/briefings/{identifier}").json()["status"]
        == "pending"
    )
    for format in ["html", "csv", "json"]:
        response = api_client.get(
            f"/api/knowledge/briefings/{identifier}/export?format={format}"
        )
        assert (
            response.status_code == 200
            and "attachment" in response.headers["content-disposition"]
        )
    assert api_client.get(f"/api/knowledge/briefings/{uuid4()}").status_code == 404
    assert (
        api_client.post(
            "/api/knowledge/briefings", json={"primary_company_id": str(uuid4())}
        ).status_code
        == 422
    )
