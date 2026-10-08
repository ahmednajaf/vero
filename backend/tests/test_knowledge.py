import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from app.core.config import Settings
from app.db.models import (
    Company,
    DocumentPage,
    DocumentTable,
    ExtractionRun,
    KnowledgeAnswer,
    KnowledgeIndex,
    KnowledgeJob,
    KnowledgePassage,
    Report,
)
from app.knowledge.contracts import AskRequest, ResearchOutput, Scope, SearchRequest
from app.knowledge.indexing import index_report, windows
from app.knowledge.inspection import inspect_source
from app.knowledge.provider import Completion, OpenAIResearchProvider, ResearchError
from app.knowledge.research import ask, packet, preview, validate_claims
from app.knowledge.workspace import company_directory, recent_answers
from app.knowledge.search import (
    adjacent_text_candidates,
    balanced_candidates,
    coverage,
    evidence,
    reports,
    search,
    topic_coverage,
)
from app.parsing.engine import canonical_json, text_hash
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def corpus(db_engine, tmp_path):
    settings = Settings(_env_file=None, reports_root=tmp_path)
    ids = []
    with Session(db_engine) as session, session.begin():
        for i, country in enumerate(["GB", "US"]):
            company = Company(
                company_name=f"Knowledge Fixture {i}",
                ticker=f"KB{i}",
                exchange="TEST",
                country=country,
                region="Test",
                sector="Industrials",
                industry="Test",
                official_domain="example.com",
                reporting_year=2025,
            )
            session.add(company)
            session.flush()
            data = f"%PDF-fixture-{i}".encode()
            (tmp_path / f"{i}.pdf").write_bytes(data)
            report = Report(
                company_id=company.id,
                title=f"Fixture annual report {i}",
                report_type="annual",
                requested_year=2025,
                detected_year=2025,
                reporting_year=None,
                source_url=f"https://example.com/{i}.pdf",
                source_policy="official",
                status="downloaded",
                parse_status="parsed",
                content_sha256=hashlib.sha256(data).hexdigest(),
                storage_key=f"{i}.pdf",
                page_count=2,
            )
            session.add(report)
            session.flush()
            run = ExtractionRun(
                report_id=report.id,
                stage="parsing",
                status="succeeded",
                idempotency_key=uuid4().hex,
                input_sha256=report.content_sha256,
                schema_version="fixture",
                code_version="fixture",
                output_summary={"warnings": []},
            )
            session.add(run)
            session.flush()
            for n, content in enumerate(
                [
                    f"Knowledge Fixture {i}\nCovering fiscal year 2024\n"
                    + "We monitor biodiversity and restore habitats. " * 180,
                    "Our supplier programme covers water scarcity.\nWe train suppliers annually."
                    if i == 0
                    else "Executive remuneration is linked to safety targets.",
                ],
                1,
            ):
                page = DocumentPage(
                    report_id=report.id,
                    parse_run_id=run.id,
                    page_number=n,
                    width_points=600,
                    height_points=800,
                    rotation=0,
                    raw_text=content,
                    ordered_text=content,
                    raw_text_sha256=text_hash(content),
                    ordered_text_sha256=text_hash(content),
                    text_characters=len(content),
                    status="parsed",
                    headings=[],
                    layout={},
                    warnings=[],
                    parser_name="fixture",
                    parser_version="1",
                )
                session.add(page)
                session.flush()
                if n == 2:
                    cells = [
                        ["Energy source", "2024", "2025"],
                        ["Renewable electricity", None, "42"],
                    ]
                    session.add(
                        DocumentTable(
                            document_page_id=page.id,
                            report_id=report.id,
                            parse_run_id=run.id,
                            page_number=n,
                            table_index=0,
                            row_count=2,
                            column_count=3,
                            cells=cells,
                            bbox=[0, 0, 100, 100],
                            cell_bboxes=[],
                            header_metadata={},
                            extraction_metadata={},
                            content_sha256=text_hash(canonical_json(cells)),
                            extraction_method="fixture",
                            parser_version="1",
                        )
                    )
            ids.append((company.id, report.id, run.id))
    for _, report_id, _ in ids:
        index_report(db_engine, report_id, settings)
    return settings, ids


def test_lossless_page_windows():
    original = ("row\n" * 1500) + "END"
    parts = list(windows(original))
    assert "".join(p[2] for p in parts) == original
    assert all(end - start <= 4000 for start, end, _ in parts)


def test_old_reports_for_newly_collected_company_are_not_promoted(db_engine, corpus):
    _, ids = corpus
    with Session(db_engine) as session, session.begin():
        session.add(
            Report(
                company_id=ids[0][0],
                title="Old unrelated source",
                requested_year=2025,
                report_type="annual",
                source_url="https://example.com/old.pdf",
                source_policy="official",
                status="downloaded",
            )
        )
    with Session(db_engine) as session:
        result = reports(session, Scope())
        assert len(result["items"]) == 2
        assert result["coverage"]["official_reports_downloaded"] == 2
        assert all(r["title"] != "Old unrelated source" for r in result["items"])


def test_full_content_index_is_idempotent_and_table_cells_preserved(db_engine, corpus):
    settings, ids = corpus
    assert index_report(db_engine, ids[0][1], settings)["status"] == "unchanged"
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeIndex)) == 2
        index = session.scalar(
            select(KnowledgeIndex).where(KnowledgeIndex.report_id == ids[0][1])
        )
        pages = list(
            session.scalars(
                select(DocumentPage)
                .where(DocumentPage.report_id == ids[0][1])
                .order_by(DocumentPage.page_number)
            )
        )
        for page in pages:
            pieces = session.scalars(
                select(KnowledgePassage)
                .where(
                    KnowledgePassage.page_id == page.id, KnowledgePassage.kind == "text"
                )
                .order_by(KnowledgePassage.ordinal)
            )
            assert "".join(p.content for p in pieces) == page.raw_text
        assert index.quality["pages_total"] == 2
        rows = list(
            session.scalars(
                select(KnowledgePassage.content).where(
                    KnowledgePassage.index_id == index.id,
                    KnowledgePassage.kind == "table",
                )
            )
        )
        assert any('null, "42"' in r for r in rows)


def test_arbitrary_topics_search_scope_pagination_and_page_evidence(db_engine, corpus):
    _, ids = corpus
    with Session(db_engine) as session:
        first = search(session, SearchRequest(query="biodiversity", limit=1))
        second = search(session, SearchRequest(query="biodiversity", limit=1, offset=1))
        assert (
            first["total"] >= 2
            and first["items"][0]["evidence_id"] != second["items"][0]["evidence_id"]
        )
        assert first["coverage"]["reports_indexed"] == 2
        scoped = search(
            session, SearchRequest(query="biodiversity", country="US", report_year=2025)
        )
        assert {r["company_id"] for r in scoped["items"]} == {str(ids[1][0])}
        assert all(r["reporting_year"] is None for r in scoped["items"])
        supplier = search(
            session, SearchRequest(query="supplier water", company_ids=[ids[0][0]])
        )
        item = supplier["items"][0]
        detail = evidence(session, item["evidence_id"])
        assert detail["page"] == 2 and detail["tables"][0]["cells"][1][1] is None
        assert detail["review_state"] == "unreviewed_source_text"
        assert search(session, SearchRequest(query="volcano"))["total"] == 0
        assert search(session, SearchRequest(query="the and"))["total"] == 0


def test_coverage_is_search_coverage_not_disclosure_claim(db_engine, corpus):
    with Session(db_engine) as session:
        result = topic_coverage(session, SearchRequest(query="supplier"))
        assert [r["status"] for r in result["items"]] == [
            "matches_found",
            "not_found_in_index",
        ]
        assert "does not establish" in result["meaning"]


def test_supporting_sources_remain_searchable_but_not_primary_coverage(
    db_engine, corpus
):
    _, ids = corpus
    with Session(db_engine) as session, session.begin():
        session.get(Report, ids[0][1]).title = "2025 CEO message"
    with Session(db_engine) as session:
        result = search(session, SearchRequest(query="supplier"))
        assert result["items"][0]["document_role"] == "supporting_document"
        counts = result["coverage"]
        assert counts["reports_indexed"] == 2
        assert counts["primary_report_candidates_indexed"] == 1
        assert counts["supporting_documents_indexed"] == 1
        assert counts["companies_with_primary_report_candidates"] == 1


def test_unknown_report_year_never_uses_requested_year_as_evidence(db_engine, corpus):
    _, ids = corpus
    with Session(db_engine) as session, session.begin():
        session.get(Report, ids[0][1]).detected_year = None
    with Session(db_engine) as session:
        assert search(session, SearchRequest(query="supplier"))["items"]
        assert not search(session, SearchRequest(query="supplier", report_year=2025))[
            "items"
        ]
        assert coverage(session, Scope(report_year=2025))["reports_indexed"] == 1


def test_stale_report_or_new_parse_is_hidden(db_engine, corpus):
    settings, ids = corpus
    with Session(db_engine) as session, session.begin():
        report = session.get(Report, ids[0][1])
        report.content_sha256 = "b" * 64
    with Session(db_engine) as session:
        assert coverage(session, Scope())["reports_indexed"] == 1
    with pytest.raises(ValueError, match="current_parse_required"):
        index_report(db_engine, ids[0][1], settings)
    with Session(db_engine) as session, session.begin():
        report = session.get(Report, ids[1][1])
        session.add(
            ExtractionRun(
                report_id=report.id,
                stage="parsing",
                status="running",
                idempotency_key=uuid4().hex,
                input_sha256=report.content_sha256,
                schema_version="fixture",
                code_version="fixture",
                created_at=datetime.now(UTC) + timedelta(seconds=1),
            )
        )
    with Session(db_engine) as session:
        assert coverage(session, Scope())["reports_indexed"] == 0


def test_disk_checksum_and_page_checksums_fail_closed(db_engine, corpus):
    settings, ids = corpus
    (settings.reports_root / "0.pdf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="source_checksum_mismatch"):
        index_report(db_engine, ids[0][1], settings)
    with pytest.raises(IntegrityError, match="immutable"):
        with Session(db_engine) as session, session.begin():
            page = session.scalar(
                select(DocumentPage).where(DocumentPage.report_id == ids[1][1]).limit(1)
            )
            page.ordered_text_sha256 = "f" * 64
    assert index_report(db_engine, ids[1][1], settings)["status"] == "unchanged"


def ai_settings(**updates):
    return Settings(
        _env_file=None,
        knowledge_ai_enabled=True,
        openai_api_key=SecretStr("unit-test-not-a-key"),
        openai_model="fixture-model",
        openai_allowed_models=["fixture-model"],
        openai_input_price=2,
        openai_output_price=10,
        knowledge_monthly_budget_usd=updates.pop("budget", 5),
        **updates,
    )


def response_payload():
    return {
        "status": "answered",
        "claims": [
            {
                "text": "The report describes supplier training.",
                "citations": [
                    {"evidence_id": "source-1", "quote": "We train suppliers annually."}
                ],
            }
        ],
    }


def test_grounding_rejects_missing_citation_fabricated_quote_number_and_census():
    source = [{"evidence_id": "source-1", "text": "We train suppliers annually."}]
    assert (
        len(validate_claims(ResearchOutput.model_validate(response_payload()), source))
        == 1
    )
    for change, code in [
        ("We train 900 suppliers.", "unsupported_number"),
        ("All companies train suppliers.", "population_claim_requires_assessment"),
    ]:
        payload = response_payload()
        payload["claims"][0]["text"] = change
        with pytest.raises(ResearchError, match=code):
            validate_claims(ResearchOutput.model_validate(payload), source)
    with pytest.raises(ResearchError, match="unsupported_citation"):
        validate_claims(ResearchOutput.model_validate(response_payload()), [])
    with pytest.raises(ResearchError, match="unsupported_citation"):
        validate_claims(
            ResearchOutput.model_validate(response_payload()),
            [{"evidence_id": "source-1", "text": "Wrong quote"}],
        )


def test_openai_provider_strict_response_and_no_tools_or_storage():
    def handler(request):
        assert request.url == "https://api.openai.com/v1/responses"
        body = json.loads(request.content)
        assert body["store"] is False and "tools" not in body
        assert body["text"]["format"]["strict"] is True
        assert body["model"] == "fixture-model"
        assert body["service_tier"] == "default"
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "fixture-model",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(response_payload()),
                            }
                        ],
                    }
                ],
            },
        )

    result = asyncio.run(
        OpenAIResearchProvider(ai_settings(), httpx.MockTransport(handler)).analyse(
            {"evidence": []}
        )
    )
    assert result.input_tokens == 100 and result.data.status == "answered"


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "openai_authentication"),
        (403, "openai_access_denied"),
        (429, "openai_rate_limit"),
        (500, "openai_unavailable"),
        (302, "openai_unavailable"),
    ],
)
def test_provider_errors_are_safe_and_never_retry(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="secret report text and key")

    with pytest.raises(ResearchError, match=code) as exc:
        asyncio.run(
            OpenAIResearchProvider(ai_settings(), httpx.MockTransport(handler)).analyse(
                {}
            )
        )
    assert len(calls) == 1 and "secret" not in str(exc.value)


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"status": "incomplete"}, "openai_incomplete_response"),
        (
            {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "refusal"}]}],
            },
            "openai_refusal",
        ),
        ({"status": "completed", "output": []}, "openai_malformed_output"),
    ],
)
def test_provider_rejects_incomplete_and_refusal(payload, code):
    with pytest.raises(ResearchError, match=code):
        asyncio.run(
            OpenAIResearchProvider(
                ai_settings(),
                httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
            ).analyse({})
        )


def test_provider_timeout_and_disabled_make_no_silent_fallback():
    def timeout(request):
        raise httpx.ReadTimeout("private", request=request)

    with pytest.raises(ResearchError, match="openai_timeout"):
        asyncio.run(
            OpenAIResearchProvider(ai_settings(), httpx.MockTransport(timeout)).analyse(
                {}
            )
        )
    with pytest.raises(ResearchError, match="hosted_ai_disabled"):
        asyncio.run(
            OpenAIResearchProvider(
                Settings(_env_file=None), httpx.MockTransport(timeout)
            ).analyse({})
        )


class MockProvider:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail
        self.plan_calls = 0

    async def plan(self, payload):
        from app.knowledge.contracts import ResearchPlan

        self.plan_calls += 1
        return Completion(
            ResearchPlan.from_question(payload["question"]),
            100,
            50,
            10,
            "fixture-model",
        )

    async def analyse(self, payload):
        self.calls += 1
        if self.fail:
            raise ResearchError("openai_timeout")
        source = next(
            s
            for s in payload["evidence"]
            if "We train suppliers annually." in s["text"]
        )
        answer = response_payload()
        answer["claims"][0]["citations"][0]["evidence_id"] = source["evidence_id"]
        return Completion(
            ResearchOutput.model_validate(answer), 100, 50, 20, "fixture-model"
        )


def test_real_db_research_cache_provenance_and_cost_no_metric_writes(db_engine, corpus):
    provider = MockProvider()
    with Session(db_engine, expire_on_commit=False) as session:
        req = AskRequest(question="How are suppliers trained?")
        first = asyncio.run(ask(session, req, ai_settings(), provider))
        second = asyncio.run(ask(session, req, ai_settings(), provider))
        assert first["claims"][0]["citations"][0]["page"] == 2
        assert second["cached"] and provider.calls == 1
        assert first["review_state"] == "ai_generated_citations_checked"
        assert first["coverage"]["exhaustive"] is False
        assert session.scalar(select(func.count()).select_from(KnowledgeAnswer)) == 1
        assert float(first["estimated_cost_usd"]) == pytest.approx(0.0014)
        assert provider.plan_calls == 1
        assert [c["stage"] for c in first["usage"]["calls"]] == [
            "planning",
            "synthesis",
        ]


def test_company_directory_preserves_uncollected_and_stale_coverage(db_engine, corpus):
    _, ids = corpus
    missing_id = uuid4()
    with Session(db_engine) as session, session.begin():
        session.add(
            Company(
                id=missing_id,
                company_name="Uncollected Fixture",
                ticker="UNCL",
                exchange="TEST",
                country="GB",
                region="Test",
                sector="Industrials",
                industry="Test",
                official_domain="example.org",
                reporting_year=2025,
            )
        )
        session.flush()
        session.add(
            KnowledgeJob(company_id=missing_id, year=2025, status="unavailable")
        )
        result = company_directory(session)
        assert result["total"] == 3
        first = next(c for c in result["items"] if c["id"] == str(ids[0][0]))
        assert first["reports_downloaded"] == first["reports_indexed"] == 1
        assert first["pages_indexed"] == 2
        assert first["availability"] == "searchable"
        absent = next(c for c in result["items"] if c["ticker"] == "UNCL")
        assert absent["availability"] == "not_collected"
        assert absent["reports_downloaded"] == absent["reports_indexed"] == 0
        session.get(Report, ids[0][1]).content_sha256 = "f" * 64
        session.flush()
        changed = next(
            c for c in company_directory(session)["items"] if c["id"] == first["id"]
        )
        assert changed["availability"] == "downloaded"
        assert changed["reports_indexed"] == 0


def test_followup_retrieves_fresh_evidence_keeps_scope_history_and_cache(
    db_engine, corpus
):
    _, ids = corpus
    provider = MockProvider()
    with Session(db_engine, expire_on_commit=False) as session:
        scope = {"company_ids": [ids[0][0]]}
        first = asyncio.run(
            ask(
                session,
                AskRequest(question="How are suppliers trained?", **scope),
                ai_settings(),
                provider,
            )
        )
        followup = AskRequest(
            question="What about their water programme?",
            parent_answer_id=first["answer_id"],
            **scope,
        )
        payload, _ = packet(session, followup, ai_settings())
        assert payload["previous_questions"] == ["How are suppliers trained?"]
        assert payload["evidence"] and "claims" not in payload
        assert all(s["company_id"] == str(ids[0][0]) for s in payload["evidence"])
        answer = asyncio.run(ask(session, followup, ai_settings(), provider))
        assert answer["parent_answer_id"] == first["answer_id"]
        assert answer["request_scope"]["company_ids"] == [str(ids[0][0])]
        cached = asyncio.run(ask(session, followup, ai_settings(), provider))
        assert cached["cached"] and provider.calls == 2
        history = recent_answers(session)["items"]
        assert (
            len(history) == 2 and history[0]["parent_answer_id"] == first["answer_id"]
        )
        with pytest.raises(ResearchError, match="conversation_scope_changed"):
            packet(
                session,
                AskRequest(
                    question="What about suppliers?",
                    parent_answer_id=first["answer_id"],
                ),
                ai_settings(),
            )
        with pytest.raises(ResearchError, match="conversation_not_found"):
            packet(
                session,
                AskRequest(question="What about suppliers?", parent_answer_id=uuid4()),
                ai_settings(),
            )


def test_workspace_api_directory_history_and_invalid_parent(api_client, corpus):
    directory = api_client.get("/api/knowledge/companies").json()
    assert directory["total"] == 2
    assert all(c["availability"] == "searchable" for c in directory["items"])
    assert api_client.get("/api/knowledge/answers").json() == {"items": []}
    response = api_client.post(
        "/api/knowledge/preview",
        json={"question": "What about suppliers?", "parent_answer_id": str(uuid4())},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "conversation_not_found"}}


@pytest.mark.parametrize(
    "provider_code,code",
    [
        ("billing_not_active", "openai_billing_not_active"),
        ("insufficient_quota", "openai_quota_exhausted"),
        ("rate_limit_exceeded", "openai_rate_limit"),
    ],
)
def test_provider_billing_errors_are_safe_and_never_retried(provider_code, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            429,
            json={"error": {"code": provider_code, "message": "private-secret-text"}},
        )

    with pytest.raises(ResearchError) as error:
        asyncio.run(
            OpenAIResearchProvider(ai_settings(), httpx.MockTransport(handler)).analyse(
                {}
            )
        )
    assert error.value.code == code and len(calls) == 1
    assert "private-secret-text" not in str(error.value)


def test_budget_failure_no_network_and_timeout_retains_reservation(db_engine, corpus):
    provider = MockProvider(fail=True)
    with Session(db_engine, expire_on_commit=False) as session:
        req = AskRequest(question="How are suppliers trained?")
        with pytest.raises(ResearchError, match="monthly_budget_exceeded"):
            asyncio.run(ask(session, req, ai_settings(budget=0.000001), provider))
        assert provider.calls == 0
        with pytest.raises(ResearchError, match="openai_timeout"):
            asyncio.run(ask(session, req, ai_settings(), provider))
        saved = session.scalar(select(KnowledgeAnswer))
        assert (
            saved.status == "failed"
            and saved.charged_usd is None
            and saved.reserved_usd > 0
        )


def test_model_settings_are_part_of_the_answer_cache(db_engine, corpus):
    provider = MockProvider()
    with Session(db_engine, expire_on_commit=False) as session:
        req = AskRequest(question="How are suppliers trained?")
        asyncio.run(ask(session, req, ai_settings(), provider))
        changed = ai_settings(openai_reasoning_effort="low")
        result = asyncio.run(ask(session, req, changed, provider))
        assert not result["cached"] and provider.calls == 2
        result = asyncio.run(ask(session, req, changed, provider))
        assert result["cached"] and provider.calls == 2
        asyncio.run(
            ask(session, req, ai_settings(openai_max_output_tokens=4000), provider)
        )
        assert provider.calls == 3


def test_count_question_not_blanket_blocked_and_empty_search_skips_synthesis(
    db_engine, corpus
):
    provider = MockProvider()
    with Session(db_engine) as session:
        result = asyncio.run(
            ask(
                session,
                AskRequest(question="How many companies train suppliers?"),
                ai_settings(),
                provider,
            )
        )
        assert result["claims"] and provider.calls == 1
        result = asyncio.run(
            ask(
                session,
                AskRequest(question="Explain volcanoes"),
                ai_settings(),
                provider,
            )
        )
        assert result["status"] == "insufficient_evidence" and provider.calls == 1
        assert result["notes"] and provider.plan_calls == 2


def test_api_search_evidence_disabled_ai_and_safe_status(api_client, corpus):
    response = api_client.post("/api/knowledge/search", json={"query": "supplier"})
    assert response.status_code == 200 and response.json()["items"]
    identifier = response.json()["items"][0]["evidence_id"]
    assert api_client.get(f"/api/knowledge/evidence/{identifier}").json()["page"] == 2
    assert api_client.get(f"/api/knowledge/evidence/{uuid4()}").status_code == 404
    assert (
        api_client.post(
            "/api/knowledge/search", json={"query": "supplier", "limit": 501}
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            "/api/knowledge/ask", json={"question": "Explain supplier programmes"}
        ).status_code
        == 503
    )
    body = api_client.get("/api/knowledge/status").json()
    assert body["reports_indexed"] == 2 and body["research"]["enabled"] is False
    assert "key" not in json.dumps(body)


def test_ingestion_jobs_idempotent_skip_success_and_resume_failure(
    db_engine, corpus, monkeypatch
):
    from app.knowledge import ingestion

    settings, ids = corpus
    jobs = ingestion.queue(db_engine, [i[0] for i in ids], 2025)
    assert jobs == ingestion.queue(db_engine, [i[0] for i in ids], 2025)
    monkeypatch.setattr(
        ingestion, "parse_report", lambda *a, **kw: {"status": "unchanged"}
    )
    results = ingestion.run_jobs(
        db_engine, jobs, settings, resume=False, refresh=False, reuse_retained=True
    )
    assert all(r["status"] == "succeeded" for r in results)
    assert ingestion.execute_job(db_engine, jobs[0], settings, resume=True)["reused"]
    with Session(db_engine) as session, session.begin():
        session.get(KnowledgeJob, jobs[0]).status = "failed"
    assert (
        ingestion.execute_job(db_engine, jobs[0], settings, resume=True)["status"]
        == "succeeded"
    )


def test_one_company_failure_does_not_block_next(db_engine, corpus, monkeypatch):
    from app.knowledge import ingestion

    settings, ids = corpus
    jobs = ingestion.queue(db_engine, [i[0] for i in ids], 2025)
    calls = []

    def parse(*args, **kwargs):
        calls.append(args[1])
        return {"status": "failed" if len(calls) == 1 else "unchanged"}

    monkeypatch.setattr(ingestion, "parse_report", parse)
    results = ingestion.run_jobs(
        db_engine, jobs, settings, resume=False, refresh=False, reuse_retained=True
    )
    assert [r["status"] for r in results] == ["failed", "succeeded"]


def test_old_registry_rows_are_not_new_library_members(db_engine, corpus):
    with Session(db_engine) as session, session.begin():
        session.add(
            Company(
                company_name="Old unused fixture",
                ticker="OLD",
                exchange="TEST",
                country="US",
                region="Test",
                sector="Industrials",
                industry="Test",
                official_domain="example.com",
                reporting_year=2025,
            )
        )
    with Session(db_engine) as session:
        assert coverage(session, Scope())["companies_in_scope"] == 2


def test_new_ingestion_does_not_reuse_historic_reports_without_opt_in(
    db_engine, corpus, monkeypatch
):
    from types import SimpleNamespace

    from app.knowledge import ingestion

    settings, ids = corpus
    jobs = ingestion.queue(db_engine, [ids[0][0]], 2025)
    calls = []

    def discover(*args, **kwargs):
        calls.append(True)
        return SimpleNamespace(
            id=uuid4(),
            status="unavailable",
            selection_reason="Fresh source unavailable",
        )

    monkeypatch.setattr(ingestion, "discover_company", discover)
    result = ingestion.execute_job(db_engine, jobs[0], settings)
    assert calls == [True] and result["status"] == "unavailable"


def test_explicit_source_retries_completed_job_without_unrelated_reports(
    db_engine, corpus, monkeypatch
):
    from app.knowledge import ingestion

    settings, ids = corpus
    jobs = ingestion.queue(db_engine, [ids[0][0]], 2025)
    with Session(db_engine) as session, session.begin():
        session.get(KnowledgeJob, jobs[0]).status = "succeeded"
    monkeypatch.setattr(
        ingestion, "parse_report", lambda *a, **kw: {"status": "unchanged"}
    )

    def no_crawl(*args, **kwargs):
        raise AssertionError("Explicit source must not crawl or substitute a report")

    monkeypatch.setattr(ingestion, "discover_company", no_crawl)
    result = ingestion.execute_job(
        db_engine, jobs[0], settings, source_report_ids=[ids[0][1]]
    )
    assert result["status"] == "succeeded"
    assert [r["report_id"] for r in result["outcome"]["reports"]] == [str(ids[0][1])]
    with Session(db_engine) as session:
        attempts_before = session.get(KnowledgeJob, jobs[0]).attempts
    wrong = ingestion.execute_job(
        db_engine, jobs[0], settings, source_report_ids=[ids[1][1]]
    )
    assert wrong["status"] == "failed"
    assert wrong["checkpoint_preserved"] is True
    with Session(db_engine) as session:
        stored = session.get(KnowledgeJob, jobs[0])
        assert stored.status == "succeeded"
        assert stored.outcome == result["outcome"]
        assert stored.attempts == attempts_before


def test_passage_cannot_cross_company_sources_or_forge_hash(db_engine, corpus):
    with Session(db_engine) as session:
        rows = list(session.scalars(select(KnowledgePassage).limit(2)))
        ids = corpus[1]
        other_page = session.scalar(
            select(DocumentPage.id).where(DocumentPage.report_id == ids[1][1]).limit(1)
        )
        index = session.scalar(
            select(KnowledgeIndex.id).where(KnowledgeIndex.report_id == ids[0][1])
        )
    with pytest.raises(IntegrityError, match="source identity"):
        with Session(db_engine) as session, session.begin():
            session.add(
                KnowledgePassage(
                    index_id=index,
                    page_id=other_page,
                    ordinal=999,
                    kind="text",
                    content="forged",
                    content_sha256=text_hash("forged"),
                    locator={},
                )
            )
    with pytest.raises(IntegrityError, match="source identity"):
        with Session(db_engine) as session, session.begin():
            row = session.get(KnowledgePassage, rows[0].id)
            row.content_sha256 = "f" * 64


def test_partial_pages_reported_and_readable_text_still_searchable(db_engine, corpus):
    # Existing immutable pages must stay immutable; a new parse can report OCR gaps.
    settings, ids = corpus
    with Session(db_engine) as session, session.begin():
        old = session.get(ExtractionRun, ids[0][2])
        run = ExtractionRun(
            report_id=ids[0][1],
            stage="parsing",
            status="succeeded",
            idempotency_key=uuid4().hex,
            input_sha256=old.input_sha256,
            schema_version="fixture",
            code_version="fixture",
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        )
        session.add(run)
        session.flush()
        pages = list(
            session.scalars(
                select(DocumentPage)
                .where(DocumentPage.parse_run_id == old.id)
                .order_by(DocumentPage.page_number)
            )
        )
        for page in pages:
            values = {
                c.name: getattr(page, c.name)
                for c in DocumentPage.__table__.columns
                if c.name not in {"id", "created_at", "updated_at"}
            }
            values.update(parse_run_id=run.id)
            if page.page_number == 2:
                values.update(
                    raw_text="",
                    ordered_text="",
                    text_characters=0,
                    raw_text_sha256=text_hash(""),
                    ordered_text_sha256=text_hash(""),
                    status="needs_ocr",
                )
            session.add(DocumentPage(**values))
    result = index_report(db_engine, ids[0][1], settings)
    assert result["quality"]["coverage"] == "partial_extracted_text"
    assert result["quality"]["pages_needing_ocr"] == [2]
    with Session(db_engine) as session:
        assert search(session, SearchRequest(query="biodiversity"))["items"]
        assert coverage(session, Scope())["reports_with_text_gaps"] == 1


def test_company_balancing_happens_before_global_limit(db_engine, corpus):
    settings, ids = corpus
    with Session(db_engine) as session, session.begin():
        page = session.scalar(
            select(DocumentPage).where(
                DocumentPage.parse_run_id == ids[0][2], DocumentPage.page_number == 1
            )
        )
        index = session.scalar(
            select(KnowledgeIndex).where(KnowledgeIndex.report_id == ids[0][1])
        )
        for n in range(105):
            session.add(
                KnowledgePassage(
                    index_id=index.id,
                    page_id=page.id,
                    ordinal=1000 + n,
                    kind="text",
                    content=page.raw_text,
                    content_sha256=text_hash(page.raw_text),
                    locator={
                        "start": 0,
                        "end": len(page.raw_text),
                        "layer": "raw_text",
                    },
                )
            )
    with Session(db_engine) as session:
        original = search(session, SearchRequest(query="biodiversity", limit=100))
        assert {x["company_id"] for x in original["items"]} == {str(ids[0][0])}
        payload, counts = packet(
            session, AskRequest(question="Explain biodiversity"), settings
        )
        assert {x["company_id"] for x in payload["evidence"]} == {
            str(i[0]) for i in ids
        }
        assert all(c["status"] == "supplied" for c in counts["companies"])
        assert counts["matching_passages"] == original["total"]


def test_table_and_prose_on_same_page_are_both_eligible(db_engine, corpus):
    with Session(db_engine) as session:
        found = balanced_candidates(session, SearchRequest(query="supplier renewable"))
        first = str(corpus[1][0][0])
        assert {x["kind"] for x in found["items"] if x["company_id"] == first} == {
            "text",
            "table",
        }
        assert len(
            {(x["report_id"], x["page"], x["kind"]) for x in found["items"]}
        ) == len(found["items"])


def test_layout_metadata_cannot_crowd_out_report_text(db_engine, corpus, monkeypatch):
    from app.knowledge import research

    settings, _ = corpus
    with Session(db_engine) as session:
        found = balanced_candidates(session, SearchRequest(query="biodiversity"))
        for item in found["items"]:
            item["headings"] = [{"text": "layout metadata" * 5000}]
        monkeypatch.setattr(
            research, "balanced_candidates", lambda *args, **kwargs: found
        )
        payload, counts = packet(
            session, AskRequest(question="Explain biodiversity"), settings
        )
        assert counts["companies_supplied"] == 2
        assert all("headings" not in item for item in payload["evidence"])
        assert counts["evidence_characters"] <= settings.knowledge_max_evidence_chars


def test_preview_distinguishes_missing_matches_unindexed_and_unknown_companies(
    db_engine, corpus
):
    settings, ids = corpus
    with Session(db_engine) as session, session.begin():
        company = Company(
            company_name="No indexed report",
            ticker="NONE",
            exchange="TEST",
            country="GB",
            region="Europe",
            sector="Industrials",
            industry="Test",
            official_domain="example.com",
            reporting_year=2025,
        )
        session.add(company)
        session.flush()
        missing_id = company.id
        session.add(
            KnowledgeJob(company_id=missing_id, year=2025, status="unavailable")
        )
    unknown = uuid4()
    with Session(db_engine) as session:
        result = preview(
            session,
            AskRequest(
                question="Describe supplier training",
                company_ids=[ids[0][0], ids[1][0], missing_id, unknown],
            ),
            settings,
        )
        states = {c["company_id"]: c["status"] for c in result["coverage"]["companies"]}
        assert states == {
            str(ids[0][0]): "supplied",
            str(ids[1][0]): "no_lexical_match",
            str(missing_id): "not_indexed_in_scope",
            str(unknown): "not_in_active_library_scope",
        }
        assert not result["model_called"]
        assert result["configuration_error"] == "hosted_ai_disabled"
        assert session.scalar(select(func.count()).select_from(KnowledgeAnswer)) == 0


def test_context_omissions_are_visible_and_deterministic(db_engine, corpus):
    settings, _ = corpus
    # Full provenance + either text window exceeds the deliberately tiny budget.
    settings = settings.model_copy(update={"knowledge_max_evidence_chars": 4000})
    with Session(db_engine) as session:
        request = AskRequest(question="Explain biodiversity")
        first = packet(session, request, settings)
        assert first == packet(session, request, settings)
        assert first[1]["evidence_characters"] <= 4000
        assert all(
            c["status"] == "omitted_context_limit" for c in first[1]["companies"]
        )


def test_inspection_separates_document_year_from_period_and_checks_bytes(
    db_engine, corpus
):
    settings, ids = corpus
    with Session(db_engine) as session:
        result = inspect_source(session, ids[0][1], settings, verify_file=True)
        assert result["file_checksum_check"] == "matched"
        assert result["detected_year"] == 2025 and result["reporting_year"] is None
        assert result["period_start"] is None and result["period_end"] is None
        assert (
            "Covering fiscal year 2024"
            in result["period_and_boundary_excerpts"][0]["excerpt"]
        )
        assert result["registry_name_found_in_opening_pages"]
        assert not result["metrics_validated"]
        assert not session.dirty and not session.new
    (settings.reports_root / "0.pdf").write_bytes(b"changed file")
    with Session(db_engine) as session:
        assert (
            inspect_source(session, ids[0][1], settings, verify_file=True)[
                "file_checksum_check"
            ]
            == "mismatch"
        )


def test_inspection_unsafe_path_and_unknown_report(db_engine, corpus):
    settings, ids = corpus
    with Session(db_engine) as session, session.begin():
        session.get(Report, ids[0][1]).storage_key = "../unrelated.pdf"
    with Session(db_engine) as session:
        assert (
            inspect_source(session, ids[0][1], settings, verify_file=True)[
                "file_checksum_check"
            ]
            == "missing_or_unsafe_path"
        )
        assert inspect_source(session, uuid4(), settings) is None


def test_preview_and_inspection_api_work_without_model(api_client, corpus):
    response = api_client.post(
        "/api/knowledge/preview", json={"question": "Explain supplier programmes"}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["payload"]["evidence"] and not result["model_called"]
    assert result["source_checks"][0]["file_checksum_check"] == "not_checked"
    assert (
        api_client.get(
            f"/api/knowledge/reports/{corpus[1][0][1]}/inspection"
        ).status_code
        == 200
    )
    assert (
        api_client.get(f"/api/knowledge/reports/{uuid4()}/inspection").status_code
        == 404
    )


def test_query_concept_coverage_beats_repetition(db_engine, corpus):
    with Session(db_engine) as session:
        result = search(
            session,
            SearchRequest(
                query="biodiversity supplier water", company_ids=[corpus[1][0][0]]
            ),
        )
        # Page 1 repeats biodiversity 180 times; page 2 covers two query concepts.
        assert result["items"][0]["page"] == 2


def test_adjacent_context_preserves_page_hash_and_separate_evidence(db_engine, corpus):
    with Session(db_engine) as session:
        request = SearchRequest(query="biodiversity", company_ids=[corpus[1][0][0]])
        source = search(session, request)["items"][0]
        neighbours = adjacent_text_candidates(session, request, [source])
        assert len(neighbours) == 1
        neighbour = neighbours[0]
        assert neighbour["page"] == source["page"]
        assert neighbour["report_id"] == source["report_id"]
        assert neighbour["evidence_id"] != source["evidence_id"]
        assert neighbour["report_sha256"] == source["report_sha256"]
        assert neighbour["text_sha256"] == text_hash(neighbour["text"])
        assert neighbour["retrieval_role"] == "adjacent_same_page_context"
        assert (
            source["locator"]["start"] == neighbour["locator"]["end"]
            or source["locator"]["end"] == neighbour["locator"]["start"]
        )
        assert adjacent_text_candidates(session, request, []) == []


def test_plan_schema_is_bounded_and_strict_for_openai():
    from app.knowledge.contracts import ResearchPlan
    from app.knowledge.provider import request_body
    from pydantic import ValidationError

    plan = ResearchPlan.from_question("Compare water management")
    with pytest.raises(ValidationError):
        ResearchPlan.model_validate(plan.model_dump() | {"queries": ["water"] * 4})
    with pytest.raises(ValidationError):
        ResearchPlan.model_validate(plan.model_dump() | {"sql": "DELETE"})
    for planning in (True, False):
        schema = request_body(ai_settings(), {}, planning=planning)["text"]["format"][
            "schema"
        ]
        assert set(schema["required"]) == set(schema["properties"])
        assert schema["additionalProperties"] is False


def test_named_company_resolution_filters_and_unknown_never_widen(db_engine, corpus):
    from app.knowledge.contracts import ResearchPlan
    from app.knowledge.planning import resolve_scope

    ids = corpus[1]
    plan = ResearchPlan.from_question("Compare KB0 with KB1")
    with Session(db_engine) as session:
        resolved, detail = resolve_scope(
            session,
            AskRequest(question="Compare KB0 with KB1"),
            plan.model_copy(update={"company_names": ["KB0", "KB1"]}),
        )
        assert set(resolved.company_ids) == {i[0] for i in ids}
        assert not detail["unresolved_companies"]
        resolved, detail = resolve_scope(
            session,
            AskRequest(question="Compare KB0 with KB1", company_ids=[ids[0][0]]),
            plan.model_copy(update={"company_names": ["KB0", "KB1"]}),
        )
        assert resolved.company_ids == [ids[0][0]]
        assert detail["unresolved_companies"][0]["name"] == "KB1"
        resolved, detail = resolve_scope(
            session,
            AskRequest(question="Describe unknown company"),
            plan.model_copy(update={"company_names": ["Unknown"]}),
        )
        assert resolved.company_ids and not list(
            session.scalars(
                select(Company.id).where(Company.id.in_(resolved.company_ids))
            )
        )


def test_multi_query_retrieves_complementary_topics_with_page_provenance(
    db_engine, corpus
):
    from app.knowledge.contracts import ResearchPlan

    plan = ResearchPlan.from_question(
        "Compare water programmes and remuneration"
    ).model_copy(
        update={
            "intent": "comparison",
            "queries": ["supplier water", "executive remuneration"],
        }
    )
    with Session(db_engine) as session:
        payload, counts = packet(
            session,
            AskRequest(question="Compare water programmes and remuneration"),
            corpus[0],
            plan,
        )
        assert {s["company_id"] for s in payload["evidence"]} == {
            str(i[0]) for i in corpus[1]
        }
        assert len(counts["queries"]) == 2
        assert all(
            s["text_sha256"] == text_hash(s["text"]) for s in payload["evidence"]
        )
        assert payload["research_plan"]["intent"] == "comparison"


def test_retrieval_relevance_not_company_alphabet_controls_context(db_engine, corpus):
    from app.knowledge.contracts import ResearchPlan

    with Session(db_engine) as session, session.begin():
        session.get(Company, corpus[1][0][0]).company_name = "Zebra Relevant"
        session.get(Company, corpus[1][1][0]).company_name = "Aardvark Other"
    with Session(db_engine) as session:
        plan = ResearchPlan.from_question("supplier water biodiversity")
        payload, _ = packet(
            session, AskRequest(question="supplier water biodiversity"), corpus[0], plan
        )
        assert payload["evidence"][0]["company"] == "Zebra Relevant"
        assert payload["evidence"][0]["page"] == 2


def test_phrase_retrieval_does_not_expand_net_zero_to_net_income(db_engine, corpus):
    from app.knowledge.search import terms

    assert terms("who is winning the race to net zero?") == ["net zero"]
    assert terms('"net zero"') == ["net zero"]
    assert terms('"net zero targets"') == ["net zero targets"]
    assert terms('"water withdrawal" emissions') == ["water withdrawal", "emissions"]
    with Session(db_engine) as session:
        assert not search(session, SearchRequest(query='"renewable energy"'))["items"]
        assert search(session, SearchRequest(query='"renewable electricity"'))["items"]


class PlannedMock(MockProvider):
    def __init__(self, plan, bad_claim=False):
        super().__init__()
        self.research_plan, self.bad_claim = plan, bad_claim

    async def plan(self, payload):
        self.plan_calls += 1
        return Completion(self.research_plan, 100, 50, 10, "fixture-model")

    async def analyse(self, payload):
        result = await super().analyse(payload)
        if self.bad_claim:
            result.data.claims.append(
                result.data.claims[0].model_copy(
                    update={"text": "They train 900 suppliers."}
                )
            )
        return result


def test_independent_grounded_findings_survive_unsupported_draft(db_engine, corpus):
    from app.knowledge.contracts import ResearchPlan

    provider = PlannedMock(
        ResearchPlan.from_question("supplier training"), bad_claim=True
    )
    with Session(db_engine, expire_on_commit=False) as session:
        answer = asyncio.run(
            ask(
                session,
                AskRequest(question="Explain supplier training"),
                ai_settings(),
                provider,
            )
        )
        assert answer["status"] == "partial" and len(answer["claims"]) == 1
        assert answer["validation"] == {
            "withheld_statements": 1,
            "reasons": ["unsupported_number"],
            "unmatched_numeric_tokens": ["900"],
        }
        assert all("900" not in c["text"] for c in answer["claims"])
        assert any("withheld" in note for note in answer["notes"])


def test_library_counts_are_calculated_not_inferred_from_top_passages(
    db_engine, corpus
):
    from app.knowledge.contracts import ResearchPlan

    plan = ResearchPlan.from_question(
        "How many companies are in this database?"
    ).model_copy(update={"intent": "library_coverage"})
    provider = PlannedMock(plan)
    with Session(db_engine, expire_on_commit=False) as session:
        answer = asyncio.run(
            ask(
                session,
                AskRequest(question="How many companies are in this database?"),
                ai_settings(),
                provider,
            )
        )
        assert (
            answer["status"] == "answered" and answer["calculations"][0]["value"] == 2
        )
        assert provider.plan_calls == 1 and provider.calls == 0
        assert not answer["claims"]


def test_broad_ranking_and_disclosure_questions_produce_bounded_partial_answers(
    db_engine, corpus
):
    from app.knowledge.contracts import ResearchPlan

    for intent in ("ranking", "disclosure_coverage"):
        plan = ResearchPlan.from_question("supplier training").model_copy(
            update={"intent": intent}
        )
        provider = PlannedMock(plan)
        with Session(db_engine, expire_on_commit=False) as session:
            answer = asyncio.run(
                ask(
                    session,
                    AskRequest(question=f"Explain {intent} of suppliers"),
                    ai_settings(),
                    provider,
                )
            )
            assert (
                answer["status"] == "partial" and answer["claims"] and answer["notes"]
            )


def test_no_overall_winner_accepted_even_with_verbatim_quote():
    value = response_payload()
    value["claims"][0]["text"] = "This is the overall winner."
    value["claims"][0]["citations"][0]["quote"] = "This is the overall winner."
    with pytest.raises(ResearchError, match="unsupported_overall_ranking"):
        validate_claims(
            ResearchOutput.model_validate(value),
            [{"evidence_id": "source-1", "text": "This is the overall winner."}],
        )


def test_report_quote_cannot_be_used_as_proof_of_our_calculation():
    value = response_payload()
    value["claims"][0]["text"] = "The supplied benchmark found no eligible peer cohort."
    with pytest.raises(ResearchError, match="calculation_requires_structured_source"):
        validate_claims(
            ResearchOutput.model_validate(value),
            [{"evidence_id": "source-1", "text": "We train suppliers annually."}],
        )


def test_followup_context_resolves_cited_entities_without_reusing_ai_facts(
    db_engine, corpus
):
    from app.knowledge.planning import planning_context

    with Session(db_engine, expire_on_commit=False) as session:
        result = asyncio.run(
            ask(
                session,
                AskRequest(question="How are suppliers trained?"),
                ai_settings(),
                MockProvider(),
            )
        )
        context = planning_context(
            session,
            AskRequest(
                question="What about those companies?",
                parent_answer_id=result["answer_id"],
            ),
        )
        assert context["previous_answer_companies"] == ["Knowledge Fixture 0"]
        assert "claims" not in context and "evidence" not in context
        assert context["directory"][0]["name"].startswith("Knowledge Fixture")


def test_new_unindexed_library_member_invalidates_cached_counts(db_engine, corpus):
    from app.knowledge.contracts import ResearchPlan

    plan = ResearchPlan.from_question(
        "How many companies are in the library?"
    ).model_copy(update={"intent": "library_coverage"})
    provider = PlannedMock(plan)
    with Session(db_engine, expire_on_commit=False) as session:
        request = AskRequest(question="How many companies are in the library?")
        first = asyncio.run(ask(session, request, ai_settings(), provider))
        company = Company(
            company_name="New Unindexed Company",
            ticker="NEWU",
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
        second = asyncio.run(ask(session, request, ai_settings(), provider))
        assert first["calculations"][0]["value"] == 2
        assert second["calculations"][0]["value"] == 3
        assert not second["cached"] and provider.plan_calls == 2


def test_quantitative_tool_reuses_engine_without_manufacturing_missing_values(
    db_engine, corpus
):
    from app.knowledge.contracts import ResearchPlan
    from app.knowledge.planning import benchmark_context

    plan = ResearchPlan.from_question("Compare Scope 1 in 2024").model_copy(
        update={
            "intent": "comparison",
            "metric_code": "scope_1_emissions",
            "observation_year": 2024,
        }
    )
    with Session(db_engine) as session:
        result = benchmark_context(session, Scope(company_ids=[corpus[1][0][0]]), plan)
        assert result["status"] == "no_eligible_peer_cohort"
        assert result["companies_checked"] == 1
        assert result["items"][0]["value"] is None
        assert result["items"][0]["percentile"] is None
