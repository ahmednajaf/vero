"""Shared limits using the existing call ledger. No billing/allowance claims."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import KnowledgeAnswer
from app.knowledge.provider import ResearchError


def check_limits(
    session: Session, settings: Settings, cost: Decimal, tokens: int
) -> None:
    """Hold this transaction until a durable reservation is inserted."""
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('knowledge-budget', 0))")
    )
    now = datetime.now(UTC)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spent = session.scalar(
        select(
            func.coalesce(
                func.sum(
                    func.coalesce(
                        KnowledgeAnswer.charged_usd, KnowledgeAnswer.reserved_usd
                    )
                ),
                0,
            )
        ).where(KnowledgeAnswer.created_at >= month)
    ) or Decimal(0)
    if spent + cost > Decimal(str(settings.knowledge_monthly_budget_usd)):
        raise ResearchError("monthly_budget_exceeded")
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
        if (
            row.status == "completed"
            and "input_tokens" in usage
            and "output_tokens" in usage
        ):
            used += int(str(usage["input_tokens"])) + int(str(usage["output_tokens"]))
        else:
            # Pre-existing records without token reservations fail conservatively.
            used += int(
                str(usage.get("reserved_tokens", settings.openai_daily_token_limit))
            )
    if used + tokens > settings.openai_daily_token_limit:
        raise ResearchError("daily_token_limit_exceeded")
