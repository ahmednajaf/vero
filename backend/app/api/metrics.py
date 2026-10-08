from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogue.contracts import (
    Category,
    Eligibility,
    MetricCatalogueResponse,
    MetricResponse,
)
from app.catalogue.seed import CATALOGUE_VERSION
from app.db.models import MetricDefinition
from app.db.session import get_session

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("", response_model=MetricCatalogueResponse)
def list_metrics(
    session: Annotated[Session, Depends(get_session)],
    category: Category | None = None,
    score_eligibility: Eligibility | None = None,
    catalogue_version: Annotated[
        str, Query(pattern=r"^\d+\.\d+\.\d+$", max_length=32)
    ] = CATALOGUE_VERSION,
) -> MetricCatalogueResponse:
    query = select(MetricDefinition).where(
        MetricDefinition.catalogue_version == catalogue_version,
        MetricDefinition.is_active.is_(True),
    )
    if category:
        query = query.where(MetricDefinition.category == category)
    if score_eligibility:
        query = query.where(MetricDefinition.score_eligibility == score_eligibility)
    metrics = []
    for row in session.scalars(
        query.order_by(
            MetricDefinition.category,
            MetricDefinition.metric_code,
            MetricDefinition.definition_version,
        )
    ):
        # Explicit boundary names avoid leaking ORM aliases/legacy fields or
        # returning definitions that do not satisfy the complete catalogue contract.
        metrics.append(
            MetricResponse.model_validate(
                {
                    "id": row.id,
                    "canonical_id": row.metric_code,
                    "definition_version": row.definition_version,
                    "catalogue_version": row.catalogue_version,
                    "name": row.name,
                    "description": row.description,
                    "category": row.category,
                    "evidence_kind": row.evidence_kind,
                    "data_type": row.value_type,
                    "quantity_kind": row.quantity_kind,
                    "canonical_unit": row.canonical_unit,
                    "allowed_units": row.allowed_units,
                    "aliases": row.aliases,
                    "normalisation_rule": row.normalisation_rule,
                    "comparability_warning": row.comparability_warning,
                    "score_eligibility": row.score_eligibility,
                    "preferred_direction": (
                        None if row.directionality == "none" else row.directionality
                    ),
                    "validation_constraints": row.validation_constraints,
                    "required_comparison_dimensions": row.required_comparison_dimensions,
                    "sector_applicability": row.sector_applicability,
                    "scope": row.scope,
                    "is_active": row.is_active,
                }
            )
        )
    return MetricCatalogueResponse(
        catalogue_version=catalogue_version,
        total=len(metrics),
        items=metrics,
        category_counts=dict(Counter(metric.category for metric in metrics)),
        score_eligibility_counts=dict(
            Counter(metric.score_eligibility for metric in metrics)
        ),
    )
