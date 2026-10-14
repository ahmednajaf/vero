"""Shared limits using the existing call ledger. No billing/allowance claims."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import KnowledgeAnswer
from app.knowledge.provider import ResearchError


LIMIT_ERRORS = frozenset({"monthly_budget_exceeded", "daily_token_limit_exceeded", "trial_budget_exceeded", "trial_budget_expired"})


def usage_summary(session: Session, settings: Settings) -> dict[str, Any]:
    """Read the same ledger used by enforcement; never alter or release reservations."""
    now = datetime.now(UTC)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    charged, reserved = session.execute(select(
        func.coalesce(func.sum(KnowledgeAnswer.charged_usd), 0),
        func.coalesce(func.sum(KnowledgeAnswer.reserved_usd).filter(KnowledgeAnswer.charged_usd.is_(None)), 0),
    ).where(KnowledgeAnswer.created_at >= month)).one()
    spent = charged + reserved
    # Include the last ten minutes before midnight to conservatively cover a
    # two-call research request straddling the UTC reset. Unknown outcomes retain
    # their full token reservation. Other applications' usage is NOT observable.
    day = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(minutes=10)
    used = 0
    for row in session.scalars(
        select(KnowledgeAnswer).where(
            KnowledgeAnswer.created_at >= day,
            KnowledgeAnswer.model.in_(settings.openai_allowed_models),
        )
    ):
        usage = row.usage or {}
        # A schema/length failure can still return final provider usage. Charge
        # those measured tokens, not the larger preflight reservation. Only an
        # unknown outcome needs to retain its full reservation.
        if "input_tokens" in usage and "output_tokens" in usage:
            used += int(str(usage["input_tokens"])) + int(str(usage["output_tokens"]))
        else:
            # Pre-existing records without token reservations fail conservatively.
            used += int(
                str(usage.get("reserved_tokens", settings.openai_daily_token_limit))
            )
    return {
        "monthly_accounted_usd": str(spent),
        "monthly_recorded_estimate_usd": str(charged),
        "monthly_reserved_usd": str(reserved),
        "monthly_remaining_usd": str(max(Decimal(0), Decimal(str(settings.knowledge_monthly_budget_usd)) - spent)),
        "daily_tokens_accounted": used,
        "daily_tokens_remaining": max(0, settings.openai_daily_token_limit - used),
        "daily_resets_at": (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat(),
    }


def check_limits(
    session: Session, settings: Settings, cost: Decimal, tokens: int
) -> None:
    """Hold this transaction until a durable reservation is inserted."""
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('knowledge-budget', 0))")
    )
    usage = usage_summary(session, settings)
    if Decimal(usage["monthly_accounted_usd"]) + cost > Decimal(str(settings.knowledge_monthly_budget_usd)):
        raise ResearchError("monthly_budget_exceeded")
    if usage["daily_tokens_accounted"] + tokens > settings.openai_daily_token_limit:
        raise ResearchError("daily_token_limit_exceeded")
