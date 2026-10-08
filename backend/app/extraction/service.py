"""Per-report/metric runs: bounded calls, retained candidates, atomic observations."""

import asyncio
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.catalogue.contracts import Metric
from app.catalogue.seed import load_catalogue
from app.core.config import Settings
from app.db.models import (
    Company,
    DocumentChunk,
    ExtractionRun,
    MetricDefinition,
    MetricObservation,
    Report,
    ValidationEvent,
)
from app.extraction.contracts import (
    Assessed,
    CandidateBatch,
    Passage,
    PIPELINE_VERSION,
    PROMPT_VERSION,
    QUALITY_VERSION,
    RETRIEVAL_VERSION,
    SCHEMA_VERSION,
    NORMALISATION_VERSION,
)
from app.extraction.prompts import extraction_prompt
from app.extraction.quality import assess, reconcile
from app.extraction.retrieval import retrieve
from app.llm.contracts import ExtractionError, ModelIdentity, StructuredExtractor
from app.llm.schema import output_schema
from app.llm.prompts import INSTRUCTION_VERSION


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def inputs(
    session: Session, report_id: UUID, code: str
) -> tuple[Report, ExtractionRun, MetricDefinition, Metric, list[Passage]]:
    report = session.get(Report, report_id)
    if report is None or report.status != "downloaded" or not report.content_sha256:
        raise ValueError("A downloaded, checksummed report is required")
    parsed = session.scalar(
        select(ExtractionRun)
        .where(
            ExtractionRun.report_id == report_id,
            ExtractionRun.stage == "parsing",
        )
        .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
        .limit(1)
    )
    if (
        parsed is None
        or parsed.status != "succeeded"
        or parsed.input_sha256 != report.content_sha256
    ):
        raise ValueError("Latest parse must have succeeded for this report checksum")
    metric = next((m for m in load_catalogue().metrics if m.canonical_id == code), None)
    if metric is None:
        raise ValueError("Unknown canonical metric")
    definition = session.scalar(
        select(MetricDefinition).where(
            MetricDefinition.metric_code == code,
            MetricDefinition.catalogue_version == metric.catalogue_version,
            MetricDefinition.definition_version == metric.definition_version,
            MetricDefinition.is_active.is_(True),
        )
    )
    if definition is None:
        raise ValueError("Active catalogue definition not seeded; migrate first")
    chunks = list(
        session.scalars(
            select(DocumentChunk)
            .where(
                DocumentChunk.report_id == report_id,
                DocumentChunk.parse_run_id == parsed.id,
                DocumentChunk.source_text_layer == "ordered_text",
            )
            .order_by(DocumentChunk.chunk_index)
        )
    )
    passages = []
    for chunk in chunks:
        if (
            chunk.document_page_id is None
            or chunk.physical_page_start != chunk.physical_page_end
        ):
            raise ValueError("Reparse legacy chunks for page-aware extraction")
        if sha(chunk.text) != chunk.text_sha256:
            raise ValueError("Chunk integrity check failed")
        passages.append(
            Passage(
                chunk.id,
                chunk.report_id,
                chunk.parse_run_id,
                chunk.physical_page_start,
                chunk.text,
                chunk.text_sha256,
                chunk.section_title,
                chunk.printed_page_label,
                chunk.source_char_start or 0,
            )
        )
    return report, parsed, definition, metric, passages


def assessment_json(value: Assessed) -> dict[str, Any]:
    return {
        "candidate": value.candidate.model_dump(),
        "state": value.state,
        "quality_flags": value.flags,
        "can_persist": value.can_persist,
        "normalised_value": (
            str(value.normalised_value) if value.normalised_value is not None else None
        ),
        "normalised_unit": value.normalised_unit,
        "intensity_denominator": value.denominator,
        "exact_source_excerpt": value.excerpt,
        "excerpt_chunk_start": value.excerpt_start,
        "excerpt_chunk_end": value.excerpt_end,
        "confidence": str(value.confidence),
        "confidence_components": value.components,
        "chunk_id": str(value.retrieved.passage.chunk_id),
    }


async def extract_metric(
    engine: Engine,
    report_id: UUID,
    code: str,
    year: int,
    settings: Settings,
    extractor: StructuredExtractor,
    *,
    identity: ModelIdentity | None = None,
    top_k: int = 3,
    force: bool = False,
    resume_calls: bool = False,
) -> dict[str, Any]:
    if not 1900 <= year <= 2100 or not 1 <= top_k <= 6:
        raise ValueError("Invalid extraction year or passage bound")
    identity = identity or await extractor.model_identity()
    lock_key = f"extract:{report_id}:{code}:{year}"
    with engine.connect() as connection:
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
            {"key": lock_key},
        )
        connection.commit()
        if not acquired:
            return {"report_id": str(report_id), "metric_id": code, "status": "busy"}
        try:
            with Session(connection, expire_on_commit=False) as session:
                report, parsed, definition, metric, passages = inputs(
                    session, report_id, code
                )
                selected = retrieve(passages, metric, year, top_k=top_k)
                profile = sha(
                    canonical(
                        {
                            "report_sha256": report.content_sha256,
                            "parse_run": str(parsed.id),
                            "metric": metric.model_dump(),
                            "year": year,
                            "model": identity.__dict__,
                            "pipeline": PIPELINE_VERSION,
                            "prompt": PROMPT_VERSION,
                            "schema": SCHEMA_VERSION,
                            "retrieval": RETRIEVAL_VERSION,
                            "normalisation": NORMALISATION_VERSION,
                            "quality": QUALITY_VERSION,
                            "top_k": top_k,
                            "max_output_tokens": settings.llm_max_output_tokens,
                            "max_prompt_chars": settings.llm_max_prompt_chars,
                            "context_tokens": settings.llm_context_tokens,
                            "chunks": [(str(p.chunk_id), p.sha256) for p in passages],
                        }
                    )
                )
                prior = session.scalar(
                    select(ExtractionRun)
                    .where(
                        ExtractionRun.report_id == report_id,
                        ExtractionRun.stage == "extraction",
                        ExtractionRun.parameters["profile_sha256"].astext == profile,
                        ExtractionRun.status == "succeeded",
                    )
                    .order_by(ExtractionRun.created_at.desc())
                    .limit(1)
                )
                if prior is not None and not force:
                    return {
                        "report_id": str(report_id),
                        "metric_id": code,
                        "run_id": str(prior.id),
                        "status": "unchanged",
                        "summary": prior.output_summary,
                    }
                # A released session lock with a running row means an interrupted
                # attempt. Retain partial call audits, never imply completion.
                for abandoned in session.scalars(
                    select(ExtractionRun).where(
                        ExtractionRun.report_id == report_id,
                        ExtractionRun.stage == "extraction",
                        ExtractionRun.parameters["metric_id"].astext == code,
                        ExtractionRun.parameters["year"].as_integer() == year,
                        ExtractionRun.status == "running",
                    )
                ):
                    abandoned.status, abandoned.error_code = "failed", "interrupted"
                    abandoned.finished_at = datetime.now(UTC)
                reusable: dict[str, tuple[str, dict[str, Any]]] = {}
                if resume_calls and not force:
                    for previous in session.scalars(
                        select(ExtractionRun)
                        .where(
                            ExtractionRun.report_id == report_id,
                            ExtractionRun.stage == "extraction",
                            ExtractionRun.parameters["metric_id"].astext == code,
                            ExtractionRun.parameters["year"].as_integer() == year,
                            ExtractionRun.input_sha256 == report.content_sha256,
                            ExtractionRun.status.in_(
                                ["succeeded", "failed", "cancelled"]
                            ),
                        )
                        .order_by(ExtractionRun.created_at.desc())
                    ):
                        previous_summary: dict[str, Any] = previous.output_summary or {}
                        for saved_call in previous_summary.get("calls", []):
                            if "raw_json" in saved_call and not saved_call.get(
                                "error_code"
                            ):
                                reusable.setdefault(
                                    saved_call["chunk_id"],
                                    (str(previous.id), saved_call),
                                )
                run = ExtractionRun(
                    report_id=report_id,
                    parent_run_id=parsed.id,
                    stage="extraction",
                    status="running",
                    idempotency_key=f"{profile}:{uuid4().hex}",
                    input_sha256=report.content_sha256,
                    model_provider=identity.provider,
                    model_name=identity.name,
                    model_digest=identity.digest,
                    prompt_version=PROMPT_VERSION,
                    schema_version=SCHEMA_VERSION,
                    code_version=PIPELINE_VERSION,
                    started_at=datetime.now(UTC),
                    parameters={
                        "profile_sha256": profile,
                        "metric_id": code,
                        "metric_definition_id": str(definition.id),
                        "definition_version": metric.definition_version,
                        "catalogue_version": metric.catalogue_version,
                        "year": year,
                        "top_k": top_k,
                        "parse_run_id": str(parsed.id),
                        "source_url": report.final_url or report.source_url,
                        "artifact_id": str(report.artifact_id),
                        "source_sha256": report.content_sha256,
                        "retrieval_version": RETRIEVAL_VERSION,
                        "quality_version": QUALITY_VERSION,
                        "normalisation_version": NORMALISATION_VERSION,
                        "total_chunks": len(passages),
                        "oversized_chunks_excluded": sum(
                            len(p.text) > 4200 for p in passages
                        ),
                        "all_candidates_reviewed": False,
                    },
                    output_summary={"calls": [], "assessment_count": 0},
                )
                session.add(run)
                session.commit()
                audits: list[dict[str, Any]] = []
                assessed: list[Assessed] = []
                failed = False
                for rank, candidate_passage in enumerate(selected, 1):
                    prompt = extraction_prompt(metric, year, candidate_passage)
                    passage = candidate_passage.passage
                    audit: dict[str, Any] = {
                        "rank": rank,
                        "chunk_id": str(passage.chunk_id),
                        "chunk_sha256": passage.sha256,
                        "physical_page": passage.page,
                        "section": passage.section,
                        "retrieval_score": candidate_passage.score,
                        "matched_terms": list(candidate_passage.matched_terms),
                        "prompt_name": prompt.name,
                        "prompt_version": prompt.version,
                        "prompt_text": prompt.text,
                        "source_chars": len(passage.text),
                    }
                    try:
                        cached = reusable.get(str(passage.chunk_id))
                        if cached and (
                            cached[1].get("prompt_text") == prompt.text
                            and cached[1].get("chunk_sha256") == passage.sha256
                            and cached[1].get("model_digest") == identity.digest
                            and cached[1].get("model") == identity.name
                            and cached[1].get("instruction_version")
                            == INSTRUCTION_VERSION
                            and cached[1].get("schema_sha256")
                            == sha(canonical(output_schema(CandidateBatch)))
                            and len(cached[1].get("raw_json", ""))
                            <= settings.llm_max_output_chars
                        ):
                            # Reuse ONLY the response, never stale relevance/rank.
                            # Re-run current quality and normalisation rules below.
                            for field in (
                                "response",
                                "raw_json",
                                "model",
                                "model_digest",
                                "prompt_sha256",
                                "schema_sha256",
                                "instruction_version",
                                "latency_ms",
                                "inference_latency_ms",
                                "attempts",
                            ):
                                if field in cached[1]:
                                    audit[field] = cached[1][field]
                            audit["reused_from_run_id"] = cached[0]
                            batch = CandidateBatch.model_validate_json(
                                audit["raw_json"], strict=True
                            )
                        else:
                            response = await extractor.extract_structured(
                                prompt, CandidateBatch
                            )
                            if (
                                response.model != identity.name
                                or response.model_digest != identity.digest
                            ):
                                raise ExtractionError("model_changed_during_run")
                            # Revalidate even with an injected test adapter.
                            batch = CandidateBatch.model_validate_json(
                                response.raw_json, strict=True
                            )
                            audit.update(
                                {
                                    "response": batch.model_dump(),
                                    "raw_json": response.raw_json,
                                    "model": response.model,
                                    "model_digest": response.model_digest,
                                    "prompt_sha256": response.prompt_sha256,
                                    "schema_sha256": response.schema_sha256,
                                    "instruction_version": response.instruction_version,
                                    "latency_ms": response.latency_ms,
                                    "inference_latency_ms": response.inference_latency_ms,
                                    "attempts": response.attempts,
                                }
                            )
                        assessed.extend(
                            assess(metric, year, candidate_passage, c)
                            for c in batch.candidates
                        )
                    except asyncio.CancelledError:
                        audit["error_code"] = "cancelled"
                        run.output_summary = {
                            "calls": [*audits, audit],
                            "assessment_count": len(assessed),
                        }
                        run.status, run.error_code = "cancelled", "cancelled"
                        run.finished_at = datetime.now(UTC)
                        session.commit()
                        raise
                    except (ExtractionError, ValueError) as exc:
                        failed = True
                        audit["error_code"] = (
                            exc.code
                            if isinstance(exc, ExtractionError)
                            else "schema_validation_failed"
                        )
                    audits.append(audit)
                    # Checkpoint each call; a crash never erases previous responses.
                    run.output_summary = {
                        "calls": audits,
                        "assessment_count": len(assessed),
                    }
                    session.commit()
                reconcile(assessed)
                if failed:
                    for item in assessed:
                        if item.can_persist:
                            item.flags.append("incomplete_candidate_run")
                            item.state = "needs_review"
                observations: list[str] = []
                unique: set[str] = set()
                for index, item in enumerate(assessed):
                    if not item.can_persist:
                        continue
                    candidate, passage = item.candidate, item.retrieved.passage
                    signature = canonical(
                        [str(passage.chunk_id), candidate.model_dump()]
                    )
                    if signature in unique:
                        continue
                    unique.add(signature)
                    observation = MetricObservation(
                        company_id=report.company_id,
                        report_id=report_id,
                        document_chunk_id=passage.chunk_id,
                        extraction_run_id=run.id,
                        metric_definition_id=definition.id,
                        idempotency_key=f"{run.id}:{index}",
                        reporting_year=year,
                        source_url=report.final_url or report.source_url,
                        source_physical_page=passage.page,
                        source_printed_page_label=passage.printed_page,
                        supporting_excerpt=item.excerpt or "",
                        extraction_method=(
                            "openai_structured_llm"
                            if identity.provider == "openai"
                            else "local_structured_llm"
                        ),
                        confidence=item.confidence,
                        confidence_notes=canonical(
                            {
                                "heuristic_not_probability": True,
                                "components": item.components,
                                "model_self_confidence": candidate.confidence,
                            }
                        ),
                        validation_state=item.state,
                        notes=canonical(
                            {
                                "quality_flags": item.flags,
                                "model_notes": candidate.notes,
                                "reporting_period_raw": candidate.reporting_period,
                                "model_status": candidate.status,
                                "assessment_index": index,
                                "chunk_sha256": passage.sha256,
                                "excerpt_chunk_start": item.excerpt_start,
                                "excerpt_chunk_end": item.excerpt_end,
                                "excerpt_page_start": passage.page_offset
                                + (item.excerpt_start or 0),
                                "excerpt_page_end": passage.page_offset
                                + (item.excerpt_end or 0),
                                "year_context_chunk_spans": [
                                    [match.start(), match.end()]
                                    for match in re.finditer(
                                        rf"\b{year}\b", passage.text
                                    )
                                ],
                            }
                        ),
                        raw_value=candidate.reported_value,
                        raw_unit=candidate.reported_unit,
                        normalised_value=item.normalised_value,
                        normalised_unit=item.normalised_unit,
                        normalisation_rule_version=(
                            NORMALISATION_VERSION
                            if item.normalised_value is not None
                            else None
                        ),
                        organisational_boundary=(
                            candidate.boundary
                            if "boundary_not_in_chunk" not in item.flags
                            else None
                        ),
                        scope=(
                            metric.scope
                            if metric.canonical_id.startswith("scope_")
                            else None
                        ),
                        scope2_method=(
                            "location_based"
                            if code == "scope_2_location_based"
                            else (
                                "market_based"
                                if code == "scope_2_market_based"
                                else None
                            )
                        ),
                        intensity_denominator=item.denominator,
                        compatibility_state=(
                            "not_comparable"
                            if item.state == "not_comparable"
                            else "unchecked"
                        ),
                        compatibility_rule_version=QUALITY_VERSION,
                    )
                    session.add(observation)
                    session.flush()
                    observations.append(str(observation.id))
                    session.add(
                        ValidationEvent(
                            metric_observation_id=observation.id,
                            new_state=item.state,
                            rule_code="extraction_quality",
                            rule_version=QUALITY_VERSION,
                            actor_type="rule",
                            actor_reference=PIPELINE_VERSION,
                            reason="Candidate evidence gates applied; no human approval or benchmark admission",
                            details={
                                "quality_flags": item.flags,
                                "assessment_index": index,
                                "confidence_components": item.components,
                            },
                        )
                    )
                summary: dict[str, Any] = {
                    "calls": audits,
                    "assessments": [assessment_json(item) for item in assessed],
                    "observation_ids": observations,
                    "observation_count": len(observations),
                    "assessment_count": len(assessed),
                    "persisted_states": dict(
                        Counter(item.state for item in assessed if item.can_persist)
                    ),
                    "retrieval_outcome": (
                        "candidates_found" if selected else "no_candidates_needs_review"
                    ),
                    "report_absence_established": False,
                    "automatically_validated": 0,
                }
                run.output_summary = summary
                run.status = "failed" if failed else "succeeded"
                run.error_code = "candidate_call_failed" if failed else None
                run.finished_at = datetime.now(UTC)
                session.commit()
                return {
                    "report_id": str(report_id),
                    "metric_id": code,
                    "run_id": str(run.id),
                    "status": run.status,
                    "summary": summary,
                }
        finally:
            connection.rollback()
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                {"key": lock_key},
            )
            connection.commit()


def observation_provenance(
    session: Session, run_ids: list[UUID] | None = None
) -> list[dict[str, Any]]:
    query = (
        select(
            MetricObservation,
            MetricDefinition,
            Report,
            Company,
            DocumentChunk,
            ExtractionRun,
        )
        .join(
            MetricDefinition,
            MetricObservation.metric_definition_id == MetricDefinition.id,
        )
        .join(Report, MetricObservation.report_id == Report.id)
        .join(
            Company,
            MetricObservation.company_id == Company.id,
        )
        .join(DocumentChunk, MetricObservation.document_chunk_id == DocumentChunk.id)
        .join(
            ExtractionRun,
            MetricObservation.extraction_run_id == ExtractionRun.id,
        )
        .where(ExtractionRun.code_version.startswith("metric-extraction-"))
    )
    if run_ids is not None:
        query = query.where(ExtractionRun.id.in_(run_ids))
    result = []
    for obs, definition, report, company, chunk, run in session.execute(
        query.order_by(
            Company.company_name,
            MetricObservation.reporting_year,
            MetricDefinition.metric_code,
            MetricObservation.source_physical_page,
            MetricObservation.id,
        )
    ):
        result.append(
            {
                "observation_id": str(obs.id),
                "company_id": str(company.id),
                "company": company.company_name,
                "metric_id": definition.metric_code,
                "metric_definition_id": str(definition.id),
                "definition_version": definition.definition_version,
                "reporting_year": obs.reporting_year,
                "raw_value": obs.raw_value,
                "raw_unit": obs.raw_unit,
                "normalised_value": (
                    str(obs.normalised_value)
                    if obs.normalised_value is not None
                    else None
                ),
                "normalised_unit": obs.normalised_unit,
                "normalisation_rule_version": obs.normalisation_rule_version,
                "boundary": obs.organisational_boundary,
                "intensity_denominator": obs.intensity_denominator,
                "source_url": obs.source_url,
                "report_id": str(report.id),
                "document_title": report.title,
                "document_sha256": report.content_sha256,
                "storage_key": report.storage_key,
                "physical_page": obs.source_physical_page,
                "printed_page_label": obs.source_printed_page_label,
                "chunk_id": str(chunk.id),
                "chunk_sha256": chunk.text_sha256,
                "parse_run_id": str(chunk.parse_run_id),
                "supporting_excerpt": obs.supporting_excerpt,
                "extraction_run_id": str(run.id),
                "extraction_method": obs.extraction_method,
                "model": run.model_name,
                "model_digest": run.model_digest,
                "prompt_version": run.prompt_version,
                "schema_version": run.schema_version,
                "extracted_at": (
                    run.finished_at.isoformat() if run.finished_at else None
                ),
                "confidence": str(obs.confidence),
                "confidence_notes": json.loads(obs.confidence_notes or "{}"),
                "validation_state": obs.validation_state,
                "compatibility_state": obs.compatibility_state,
                "notes": json.loads(obs.notes),
                "validation_events": [
                    {
                        "id": str(event.id),
                        "previous_state": event.previous_state,
                        "new_state": event.new_state,
                        "rule_code": event.rule_code,
                        "rule_version": event.rule_version,
                        "actor_type": event.actor_type,
                        "actor_reference": event.actor_reference,
                        "reason": event.reason,
                        "details": event.details,
                        "created_at": event.created_at.isoformat(),
                    }
                    for event in session.scalars(
                        select(ValidationEvent)
                        .where(ValidationEvent.metric_observation_id == obs.id)
                        .order_by(ValidationEvent.created_at, ValidationEvent.id)
                    )
                ],
            }
        )
    return result
