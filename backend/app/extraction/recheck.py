"""Auditable deterministic rejection of old broad-quote scope/row mismatches."""

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import (
    ExtractionRun,
    MetricDefinition,
    MetricObservation,
    ValidationEvent,
)
from app.extraction.contracts import QUALITY_VERSION
from app.extraction.quality import scope_row_matches


def recheck_scope_rows(
    engine: Engine, run_ids: list[UUID] | None = None, limit: int = 100
) -> dict[str, Any]:
    checked = rejected = 0
    identifiers: list[str] = []
    with Session(engine) as session, session.begin():
        query = (
            select(MetricObservation, MetricDefinition.metric_code)
            .join(
                MetricDefinition,
                MetricDefinition.id == MetricObservation.metric_definition_id,
            )
            .join(
                ExtractionRun, ExtractionRun.id == MetricObservation.extraction_run_id
            )
            .where(
                ExtractionRun.code_version.startswith("metric-extraction-"),
                ExtractionRun.status.in_(["succeeded", "failed"]),
                MetricObservation.extraction_method.in_(
                    ["local_structured_llm", "openai_structured_llm"]
                ),
                MetricObservation.validation_state.in_(
                    ["extracted", "needs_review", "not_comparable"]
                ),
                MetricDefinition.metric_code.in_(
                    [
                        "scope_1_emissions",
                        "scope_2_location_based",
                        "scope_2_market_based",
                    ]
                ),
            )
        )
        if run_ids:
            query = query.where(ExtractionRun.id.in_(run_ids))
        rows = session.execute(
            query.order_by(MetricObservation.created_at, MetricObservation.id)
            .limit(limit)
            .with_for_update(of=MetricObservation)
        ).all()
        for observation, code in rows:
            prior = session.scalar(
                select(ValidationEvent.id)
                .where(
                    ValidationEvent.metric_observation_id == observation.id,
                    ValidationEvent.rule_code == "scope_row_recheck",
                    ValidationEvent.rule_version == QUALITY_VERSION,
                )
                .limit(1)
            )
            if prior is not None:
                continue
            passed = scope_row_matches(
                code, observation.supporting_excerpt, observation.raw_value or ""
            )
            previous = observation.validation_state
            before = {
                "normalised_value": (
                    str(observation.normalised_value)
                    if observation.normalised_value is not None
                    else None
                ),
                "normalised_unit": observation.normalised_unit,
                "normalisation_rule_version": observation.normalisation_rule_version,
                "confidence": str(observation.confidence),
            }
            if not passed:
                # Never replace the raw model response/value or source quote.
                # Earlier conversion remains in the immutable event and original run.
                observation.validation_state = "rejected"
                observation.compatibility_state = "not_comparable"
                observation.compatibility_rule_version = QUALITY_VERSION
                observation.normalised_value = None
                observation.normalised_unit = None
                observation.normalisation_rule_version = None
                observation.confidence = min(
                    observation.confidence or Decimal("0"), Decimal("0.25")
                )
                notes = json.loads(observation.notes)
                notes["quality_recheck"] = {
                    "rule_version": QUALITY_VERSION,
                    "flag": "scope_value_row_mismatch",
                }
                observation.notes = json.dumps(notes, ensure_ascii=False)
                rejected += 1
                identifiers.append(str(observation.id))
            session.add(
                ValidationEvent(
                    metric_observation_id=observation.id,
                    previous_state=previous,
                    new_state=observation.validation_state,
                    actor_type="rule",
                    actor_reference="source-scope-row-recheck",
                    rule_code="scope_row_recheck",
                    rule_version=QUALITY_VERSION,
                    reason=(
                        "Explicit scope/row association checked; no automatic approval"
                        if passed
                        else "The quoted value is not on the requested explicit Scope 1/2 row; raw evidence retained, unsupported conversion withdrawn"
                    ),
                    details={
                        "passed": passed,
                        "previous_conversion_and_confidence": before,
                    },
                )
            )
            checked += 1
    return {
        "checked": checked,
        "rejected": rejected,
        "rejected_observation_ids": identifiers,
        "rule_version": QUALITY_VERSION,
        "model_calls": 0,
    }
