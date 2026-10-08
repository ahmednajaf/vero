import asyncio
import json
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import KnowledgeAnswer
from app.knowledge.budget import check_limits
from app.knowledge.contracts import BRIEFING_PROMPT_PREFIX
from app.knowledge.provider import OpenAIResearchProvider, ResearchError
from app.knowledge.workspace import recent_answers
from app.llm.contracts import ExtractionError, Prompt
from app.llm.openai import OpenAIStructuredExtractor
from app.llm.prompts import SmokeResponse


def test_chat_history_excludes_internal_sections_without_deleting_cost_ledger(
    db_engine,
):
    questions = [
        "Compare the reported energy figures",
        BRIEFING_PROMPT_PREFIX + "Compare energy.",
    ]
    with Session(db_engine) as session, session.begin():
        for question in questions:
            session.add(
                KnowledgeAnswer(
                    request_sha256="0" * 64,
                    question=question,
                    provider="openai",
                    model="fixture-mini",
                    status="completed",
                    payload={},
                    reserved_usd=Decimal("0.01"),
                    usage={},
                )
            )
    with Session(db_engine) as session:
        assert [r["question"] for r in recent_answers(session)["items"]] == questions[
            :1
        ]
        assert len(session.scalars(select(KnowledgeAnswer)).all()) == 2


def settings(**kw):
    return Settings(
        _env_file=None,
        knowledge_ai_enabled=True,
        openai_model="fixture-mini",
        openai_allowed_models=["fixture-mini"],
        openai_api_key=SecretStr("fixture-key"),
        openai_input_price=0.75,
        openai_output_price=4.5,
        knowledge_monthly_budget_usd=5,
        **kw,
    )


def response(data=None):
    return {
        "status": "completed",
        "model": "fixture-mini",
        "usage": {"input_tokens": 100, "output_tokens": 25},
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            data
                            or {"company_name": "Fixture Ltd", "reporting_year": 2024}
                        ),
                    }
                ],
            }
        ],
    }


def test_model_allowlist_blocks_before_network():
    s = settings().model_copy(update={"openai_model": "unapproved-flagship"})

    def forbidden(_):
        pytest.fail("Disallowed model must not reach the network")

    provider = OpenAIResearchProvider(s, httpx.MockTransport(forbidden))
    with pytest.raises(ResearchError, match="openai_model_not_allowed"):
        asyncio.run(provider.analyse({}))


def test_extractor_uses_strict_schema_shared_ledger_and_cache(db_engine):
    calls = []

    def respond(request):
        body = json.loads(request.content)
        assert body["model"] == "fixture-mini"
        assert body["text"]["format"]["schema"]["additionalProperties"] is False
        assert body["store"] is False
        calls.append(body)
        return httpx.Response(200, json=response())

    s = settings()
    adapter = OpenAIStructuredExtractor(
        s, db_engine, OpenAIResearchProvider(s, httpx.MockTransport(respond))
    )
    prompt = Prompt("fixture-extraction", "1", "Fixture Ltd, 2024")
    first = asyncio.run(adapter.extract_structured(prompt, SmokeResponse))
    second = asyncio.run(adapter.extract_structured(prompt, SmokeResponse))
    assert first.data.company_name == "Fixture Ltd"
    assert second.data == first.data and second.attempts == 0
    assert len(calls) == 1
    with Session(db_engine) as session:
        ledger = session.scalar(select(KnowledgeAnswer))
        assert ledger.status == "completed" and ledger.usage["input_tokens"] == 100
        assert ledger.charged_usd == Decimal("0.0001875")
        assert recent_answers(session)["items"] == []


@pytest.mark.parametrize("failed", [False, True])
def test_daily_limit_counts_known_usage_and_unknown_reservations(db_engine, failed):
    s = settings(openai_daily_token_limit=1000)
    with Session(db_engine) as session:
        session.add(
            KnowledgeAnswer(
                request_sha256=uuid4().hex,
                question="Fixture",
                provider="openai",
                model=s.openai_model,
                status="failed" if failed else "completed",
                reserved_usd=0.01,
                usage={"reserved_tokens": 950}
                if failed
                else {"input_tokens": 900, "output_tokens": 50},
            )
        )
        session.commit()
        with pytest.raises(ResearchError, match="daily_token_limit_exceeded"):
            check_limits(session, s, Decimal(".01"), 51)


def test_provider_failure_is_retained_without_retry(db_engine):
    calls = []

    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout("fixture")

    s = settings()
    adapter = OpenAIStructuredExtractor(
        s, db_engine, OpenAIResearchProvider(s, httpx.MockTransport(respond))
    )
    with pytest.raises(ExtractionError, match="openai_timeout"):
        asyncio.run(
            adapter.extract_structured(
                Prompt("fixture", "1", "Fixture source"), SmokeResponse
            )
        )
    assert len(calls) == 1
    with Session(db_engine) as session:
        ledger = session.scalar(select(KnowledgeAnswer))
        assert ledger.status == "failed" and ledger.charged_usd is None
        assert ledger.usage["reserved_tokens"] > 0


def test_daily_limit_blocks_extraction_before_provider(db_engine):
    def forbidden(_):
        pytest.fail("Daily guard must run before the network")

    s = settings(openai_daily_token_limit=1)
    adapter = OpenAIStructuredExtractor(
        s, db_engine, OpenAIResearchProvider(s, httpx.MockTransport(forbidden))
    )
    with pytest.raises(ExtractionError, match="daily_token_limit_exceeded"):
        asyncio.run(
            adapter.extract_structured(Prompt("fixture", "1", "Source"), SmokeResponse)
        )
