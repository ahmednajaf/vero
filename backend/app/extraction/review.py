"""Explicit numeric source-fact review. Factual validation is NOT peer admission.

This command is not called by extraction. A reviewer must inspect the PDF table,
then supply its exact row/year/unit evidence. Files, chunks and values are checked
again before an append-only validation event is committed. No AI confidence score
can trigger this operation and no human sign-off is claimed.
"""

import hashlib
import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.catalogue.seed import load_catalogue
from app.core.config import Settings
from app.db.models import (
    DocumentChunk,
    DocumentPage,
    ExtractionRun,
    MetricDefinition,
    MetricObservation,
    Report,
    ValidationEvent,
)
from app.extraction.contracts import NORMALISATION_VERSION
from app.extraction.normalisation import normalise
from app.extraction.quality import locate_excerpt, literal_present

VERSION = "source-fact-review-v1"


class FactReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observation_id: UUID
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metric_id: str
    reporting_year: int
    source_page: int = Field(ge=1)
    raw_value: str
    raw_unit: str
    year_excerpt: str = Field(min_length=4)
    unit_excerpt: str = Field(min_length=1)
    review_note: str = Field(min_length=50)


def review_facts(
    engine: Engine, settings: Settings, path: Path
) -> list[dict[str, str]]:
    reviews = [FactReview.model_validate(row) for row in json.loads(path.read_text())]
    if len({r.observation_id for r in reviews}) != len(reviews):
        raise ValueError("Duplicate observation in review")
    catalogue = {m.canonical_id: m for m in load_catalogue().metrics}
    results = []
    with Session(engine) as session, session.begin():
        for review in reviews:
            row = session.get(
                MetricObservation, review.observation_id, with_for_update=True
            )
            if row is None or row.validation_state == "rejected":
                raise ValueError("Review requires an existing non-rejected observation")
            report = session.get(Report, row.report_id)
            chunk = session.get(DocumentChunk, row.document_chunk_id)
            definition = session.get(MetricDefinition, row.metric_definition_id)
            assert report is not None and definition is not None
            if (
                chunk is None
                or chunk.report_id != report.id
                or chunk.document_page_id is None
            ):
                raise ValueError("Page-aware chunk provenance required")
            page = session.get(DocumentPage, chunk.document_page_id)
            assert page is not None
            parsed = session.get(ExtractionRun, chunk.parse_run_id)
            if (
                parsed is None
                or parsed.status != "succeeded"
                or parsed.input_sha256 != report.content_sha256
            ):
                raise ValueError("Source parse does not match report checksum")
            if (
                definition.metric_code != review.metric_id
                or row.reporting_year != review.reporting_year
                or row.source_physical_page != review.source_page
                or page.page_number != review.source_page
                or row.raw_value != review.raw_value
                or row.raw_unit != review.raw_unit
                or report.content_sha256 != review.document_sha256
                or report.status != "downloaded"
                or report.source_policy != "official"
                or not report.storage_key
                or row.source_url not in {report.source_url, report.final_url}
            ):
                raise ValueError(
                    "Review does not match stored observation and official report"
                )
            source = (settings.reports_root / report.storage_key).resolve()
            if not source.is_relative_to(settings.reports_root.resolve()):
                raise ValueError("Unsafe artifact path")
            with source.open("rb") as document:
                if (
                    hashlib.file_digest(document, "sha256").hexdigest()
                    != review.document_sha256
                ):
                    raise ValueError("Downloaded PDF checksum mismatch")
            if (
                hashlib.sha256(chunk.text.encode()).hexdigest() != chunk.text_sha256
                or hashlib.sha256(page.ordered_text.encode()).hexdigest()
                != page.ordered_text_sha256
                or chunk.text
                != page.ordered_text[chunk.source_char_start : chunk.source_char_end]
                or locate_excerpt(chunk.text, row.supporting_excerpt) is None
                or not literal_present(review.raw_value, row.supporting_excerpt)
                or locate_excerpt(page.ordered_text, review.year_excerpt) is None
                or not literal_present(str(review.reporting_year), review.year_excerpt)
                or locate_excerpt(page.ordered_text, review.unit_excerpt) is None
                or locate_excerpt(review.unit_excerpt, review.raw_unit) is None
            ):
                raise ValueError(
                    "Source row/year/unit evidence is not an exact page-backed excerpt"
                )
            metric = catalogue[review.metric_id]
            if metric.evidence_kind != "performance" or metric.data_type not in {
                "decimal",
                "integer",
            }:
                raise ValueError(
                    "Only numeric achieved-performance facts are supported"
                )
            converted = normalise(metric, review.raw_value, review.raw_unit)
            if converted.value is None or converted.flags:
                raise ValueError("Deterministic normalisation is unresolved")
            payload = review.model_dump(mode="json")
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest()
            old = session.scalar(
                select(ValidationEvent).where(
                    ValidationEvent.metric_observation_id == row.id,
                    ValidationEvent.rule_code == VERSION,
                    ValidationEvent.details["review_sha256"].astext == digest,
                )
            )
            if (
                old
                and row.validation_state == "validated"
                and row.normalisation_rule_version == NORMALISATION_VERSION
            ):
                results.append({"observation_id": str(row.id), "status": "unchanged"})
                continue
            previous = row.validation_state
            before = {
                "normalised_value": (
                    str(row.normalised_value)
                    if row.normalised_value is not None
                    else None
                ),
                "normalised_unit": row.normalised_unit,
                "normalisation_rule_version": row.normalisation_rule_version,
            }
            row.normalised_value, row.normalised_unit = converted.value, converted.unit
            row.normalisation_rule_version = NORMALISATION_VERSION
            row.validation_state = "validated"
            row.compatibility_state = "unchecked"
            # Do not fill unknown boundaries, approve comparability or enable ranking.
            session.flush()
            session.add(
                ValidationEvent(
                    metric_observation_id=row.id,
                    previous_state=previous,
                    new_state="validated",
                    rule_code=VERSION,
                    rule_version=VERSION,
                    actor_type="rule",
                    actor_reference="codex-visual-source-review-plus-deterministic-checks",
                    reason="Numeric fact matched to the rendered source table, year and unit; no human sign-off or peer comparability approval. "
                    + review.review_note,
                    details={
                        "review_sha256": digest,
                        "source_fact_review": payload,
                        "previous_conversion": before,
                        "comparability_approved": False,
                        "human_signoff": False,
                    },
                )
            )
            results.append(
                {
                    "observation_id": str(row.id),
                    "status": "fact_validated_comparability_unchanged",
                }
            )
    return results
