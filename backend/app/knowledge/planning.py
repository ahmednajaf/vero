"""Read-only research tools. Model plans never execute code, SQL or web requests."""

import re
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    KnowledgeAnswer,
    KnowledgeIndex,
    MetricDefinition,
    MetricObservation,
    Target,
    ValidationEvent,
)
from app.knowledge.contracts import AskRequest, ResearchPlan, Scope
from app.knowledge.provider import ResearchError
from app.knowledge.search import company_scope, indexed_sources, coverage


def conversation(session: Session, request: AskRequest) -> list[str]:
    scope = request.model_dump(mode="json", exclude={"question", "parent_answer_id"})
    questions: list[str] = []
    parent_id, visited = request.parent_answer_id, set()
    while parent_id and len(questions) < 3:
        if parent_id in visited:
            raise ResearchError("invalid_conversation")
        visited.add(parent_id)
        parent = session.get(KnowledgeAnswer, parent_id)
        if not parent or parent.status != "completed":
            raise ResearchError("conversation_not_found")
        if parent.payload.get("request_scope") != scope:
            raise ResearchError("conversation_scope_changed")
        questions.insert(0, parent.question)
        value = parent.payload.get("parent_answer_id")
        parent_id = UUID(str(value)) if value else None
    return questions


def planning_context(session: Session, request: AskRequest) -> dict[str, Any]:
    previous = conversation(session, request)
    prior_sources: list[str] = []
    if request.parent_answer_id:
        parent = session.get(KnowledgeAnswer, request.parent_answer_id)
        assert parent is not None
        prior_sources = sorted(
            {
                c["company"]
                for claim in cast(
                    list[dict[str, Any]], parent.payload.get("claims", [])
                )
                for c in claim["citations"]
            }
        )
    companies = list(
        session.scalars(
            select(Company).where(*company_scope(request)).order_by(Company.id)
        )
    )
    mentioned = name_key(" ".join([request.question, *previous, *prior_sources]))

    def relevant(c: Company) -> bool:
        keys = [
            name_key(c.company_name),
            name_key(c.company_name).split()[0],
            c.ticker.casefold(),
        ]
        return c.id in request.company_ids or any(
            len(k) >= 3 and re.search(r"\b" + re.escape(k) + r"\b", mentioned)
            for k in keys
        )

    return {
        "question": request.question,
        "previous_questions": previous,
        "previous_answer_companies": prior_sources,
        "available_filters": {
            "sectors": sorted({c.sector for c in companies}),
            "countries": sorted({c.country for c in companies}),
        },
        "selected_scope": request.model_dump(
            mode="json", exclude={"question", "parent_answer_id"}
        ),
        "directory": [
            {
                "name": c.company_name,
                "ticker": c.ticker,
                "sector": c.sector,
                "country": c.country,
            }
            for c in companies
            if relevant(c)
        ],
        "metric_codes": list(
            session.scalars(
                select(MetricDefinition.metric_code).order_by(
                    MetricDefinition.metric_code
                )
            )
        ),
    }


def corpus_signature(session: Session, request: AskRequest) -> dict[str, Any]:
    # New records outside the last sampled evidence, updated validation and exact
    # library-count changes all invalidate cache; no stale metrics/counts replayed.
    indexes = sorted(
        [
            [str(row[0]), row[1]]
            for row in session.execute(
                indexed_sources(request).with_only_columns(
                    KnowledgeIndex.report_id, KnowledgeIndex.fingerprint
                )
            )
        ]
    )
    return {
        "indexes": indexes,
        "coverage": coverage(session, request),
        "companies": [
            list(map(str, row))
            for row in session.execute(
                select(
                    Company.id,
                    Company.company_name,
                    Company.ticker,
                    Company.sector,
                    Company.country,
                )
                .where(*company_scope(request))
                .order_by(Company.id)
            )
        ],
        "metric_versions": [
            str(session.scalar(select(func.max(column))))
            for column in (
                MetricObservation.updated_at,
                Target.updated_at,
                ValidationEvent.created_at,
            )
        ],
    }


def name_key(value: str) -> str:
    value = re.sub(
        r"\b(incorporated|inc|corporation|corp|plc|limited|ltd|ag|sa)\b",
        " ",
        value.casefold(),
    )
    return " ".join(re.findall(r"\w+", value.replace("&", " and ")))


def resolve_scope(
    session: Session, request: AskRequest, plan: ResearchPlan
) -> tuple[Scope, dict[str, Any]]:
    """Resolve real records and intersect filters; never widen the selected scope."""
    companies = list(
        session.scalars(
            select(Company).where(*company_scope(request)).order_by(Company.id)
        )
    )
    selected: set[UUID] = set()
    unresolved = []
    for name in plan.company_names:
        key = name_key(name)
        exact = [
            c
            for c in companies
            if key in {name_key(c.company_name), c.ticker.casefold()}
        ]
        candidates = exact or [
            c
            for c in companies
            if len(key) >= 3 and name_key(c.company_name).startswith(key + " ")
        ]
        if len(candidates) == 1:
            selected.add(candidates[0].id)
        else:
            unresolved.append(
                {
                    "name": name,
                    "reason": "ambiguous"
                    if candidates
                    else "not_in_selected_library_scope",
                    "candidates": [c.company_name for c in candidates],
                }
            )
    values = request.model_dump(exclude={"question", "parent_answer_id"})
    if plan.company_names:
        values["company_ids"] = sorted(selected, key=str) or [UUID(int=0)]
    invalid_filters = []
    for key in ("sector", "country"):
        requested = getattr(plan, key)
        if requested is None:
            continue
        available = {getattr(c, key).casefold(): getattr(c, key) for c in companies}
        if requested.casefold() not in available:
            invalid_filters.append(key)
            values["company_ids"] = [UUID(int=0)]
        elif not values[key]:
            values[key] = available[requested.casefold()]
    resolved = Scope(**values)
    return resolved, {
        "company_names": [c.company_name for c in companies if c.id in selected],
        "unresolved_companies": unresolved,
        "invalid_filters": invalid_filters,
        "scope": resolved.model_dump(mode="json"),
    }


def benchmark_context(
    session: Session, scope: Scope, plan: ResearchPlan
) -> dict[str, Any] | None:
    """Read the existing deterministic engine; never promote AI facts to metrics."""
    if (
        plan.intent not in {"comparison", "ranking"}
        or not plan.metric_code
        or not plan.observation_year
    ):
        return None
    from app.benchmarking.service import calculate

    codes = set(session.scalars(select(MetricDefinition.metric_code)))
    if plan.metric_code not in codes:
        return {"status": "unknown_metric", "metric": plan.metric_code}
    ids = list(session.scalars(select(Company.id).where(*company_scope(scope))))
    result = calculate(
        session,
        year=plan.observation_year,
        company_ids=ids,
        report_ids=scope.report_ids or None,
    )
    items = []
    for company in result["items"]:
        metric = company["metrics"].get(plan.metric_code)
        if metric:
            items.append(
                {
                    "company": company["company_name"],
                    "company_id": company["company_id"],
                    "value": metric["value"],
                    "unit": metric["unit"],
                    "eligibility_reason": metric["eligibility_reason"],
                    "peer_sample_size": metric["peer_sample_size"],
                    "median": metric["median"],
                    "percentile": metric["percentile"],
                }
            )
    return {
        "metric": plan.metric_code,
        "year": plan.observation_year,
        "peer_group": "sector",
        "minimum_peers": 5,
        "status": "available"
        if any(i["percentile"] is not None for i in items)
        else "no_eligible_peer_cohort",
        "input_sha256": result["input_sha256"],
        "companies_checked": len(items),
        "companies_with_eligible_percentile": sum(
            i["percentile"] is not None for i in items
        ),
        "items": items[:10],
        "items_truncated": len(items) > 10,
    }
