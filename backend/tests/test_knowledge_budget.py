from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import KnowledgeAnswer
from app.knowledge.budget import check_limits, usage_summary
from app.knowledge.provider import ResearchError


def record(**updates):
    return KnowledgeAnswer(**{
        "request_sha256": "a" * 64, "question": "Test", "provider": "openai",
        "model": "fixture", "status": "completed", "payload": {},
        "reserved_usd": Decimal("0.5"), "charged_usd": Decimal("0.1"),
        "usage": {"input_tokens": 100, "output_tokens": 20}, **updates,
    })


def settings(**updates):
    return Settings(_env_file=None, openai_allowed_models=["fixture"],
                    knowledge_monthly_budget_usd=1, **updates)


def test_usage_includes_unknown_reservations_but_not_settled_reservations(db_engine):
    with Session(db_engine) as session:
        session.add_all([
            record(),
            record(status="failed", charged_usd=None, usage={"reserved_tokens": 200}),
            record(charged_usd=Decimal(0)),
            record(created_at=datetime.now(UTC) - timedelta(days=40)),
        ])
        session.commit()
        usage = usage_summary(session, settings())
        assert Decimal(usage["monthly_recorded_estimate_usd"]) == Decimal("0.1")
        assert Decimal(usage["monthly_reserved_usd"]) == Decimal("0.5")
        assert Decimal(usage["monthly_accounted_usd"]) == Decimal("0.6")
        assert Decimal(usage["monthly_remaining_usd"]) == Decimal("0.4")
        assert usage["daily_tokens_accounted"] == 440
        assert session.scalar(select(KnowledgeAnswer).where(KnowledgeAnswer.charged_usd.is_(None))).reserved_usd == Decimal("0.5")


def test_displayed_usage_and_enforcement_use_identical_totals(db_engine):
    with Session(db_engine) as session:
        session.add(record())
        session.commit()
        check_limits(session, settings(), Decimal("0.9"), 100)
        with pytest.raises(ResearchError, match="monthly_budget_exceeded"):
            check_limits(session, settings(), Decimal("0.90000001"), 100)
        with pytest.raises(ResearchError, match="daily_token_limit_exceeded"):
            check_limits(session, settings(openai_daily_token_limit=200), Decimal(0), 81)


def test_status_exposes_only_safe_usage_numbers(api_client):
    response = api_client.get("/api/knowledge/status")
    assert response.status_code == 200
    usage = response.json()["research"]["usage"]
    assert usage["daily_tokens_accounted"] == 0
    assert Decimal(usage["monthly_remaining_usd"]) == 0
    assert "api_key" not in response.text and "question" not in response.text
