"""Complete snapshots, including missing companies and unapproved target evidence."""

import csv
import json
import os
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import (
    DocumentChunk,
    ExtractionRun,
    PipelineEvent,
    PipelineJob,
    PipelineRun,
    Report,
)
from app.extraction.service import observation_provenance


def snapshot(engine: Engine, run_id: UUID) -> dict[str, Any]:
    with Session(engine) as session:
        run = session.get(PipelineRun, run_id)
        assert run is not None
        jobs = list(
            session.scalars(
                select(PipelineJob)
                .where(PipelineJob.run_id == run_id)
                .order_by(
                    PipelineJob.company_id, PipelineJob.stage, PipelineJob.metric_code
                )
            )
        )
        ids = list(
            {
                UUID(str(j.result["extraction_run_id"]))
                for j in jobs
                if j.result.get("extraction_run_id")
            }
        )
        observations = observation_provenance(session, ids) if ids else []
        candidates = []
        extraction_runs = []
        for extraction in session.scalars(
            select(ExtractionRun).where(ExtractionRun.id.in_(ids))
        ):
            report = session.get(Report, extraction.report_id)
            assert report is not None
            extraction_runs.append(
                {
                    "id": str(extraction.id),
                    "status": extraction.status,
                    "parameters": extraction.parameters,
                    "summary": extraction.output_summary,
                    "error_code": extraction.error_code,
                    "model": extraction.model_name,
                    "model_digest": extraction.model_digest,
                    "prompt_version": extraction.prompt_version,
                    "schema_version": extraction.schema_version,
                }
            )
            extraction_summary: dict[str, Any] = extraction.output_summary or {}
            for assessment in extraction_summary.get("assessments", []):
                if assessment["can_persist"]:
                    continue
                c = assessment["candidate"]
                chunk = session.get(DocumentChunk, UUID(assessment["chunk_id"]))
                assert chunk is not None
                flags = assessment["quality_flags"]
                is_target = c["metric_id"] == "net_zero_target_year"
                grounded = bool(
                    assessment["exact_source_excerpt"]
                    and c["reported_value"]
                    and not {
                        "metric_mismatch",
                        "page_mismatch",
                        "value_not_in_excerpt",
                        "year_unsubstantiated",
                        "excerpt_not_in_chunk",
                        "contradictory_model_status",
                    }.intersection(flags)
                )
                candidates.append(
                    {
                        "record_kind": (
                            "target_candidate" if is_target else "withheld_candidate"
                        ),
                        "company_id": str(report.company_id),
                        "metric_id": c["metric_id"],
                        "reporting_year": extraction.parameters["year"],
                        "report_id": str(report.id),
                        "document_title": report.title,
                        "document_sha256": report.content_sha256,
                        "source_url": report.final_url or report.source_url,
                        "physical_page": chunk.physical_page_start,
                        "chunk_id": str(chunk.id),
                        "chunk_sha256": chunk.text_sha256,
                        "parse_run_id": str(chunk.parse_run_id),
                        "raw_value": c["reported_value"],
                        "raw_unit": c["reported_unit"],
                        "normalised_value": None,
                        "normalised_unit": None,
                        "supporting_excerpt": assessment["exact_source_excerpt"],
                        "model_supporting_excerpt": c["supporting_excerpt"],
                        "boundary": c["boundary"],
                        "confidence": assessment["confidence"],
                        "validation_state": (
                            "needs_review" if is_target and grounded else "rejected"
                        ),
                        "quality_flags": flags,
                        "extraction_run_id": str(extraction.id),
                        "extraction_method": "local_structured_llm",
                        "model": extraction.model_name,
                        "model_digest": extraction.model_digest,
                        "prompt_version": extraction.prompt_version,
                        "extracted_at": (
                            extraction.finished_at.isoformat()
                            if extraction.finished_at
                            else None
                        ),
                        "notes": c["notes"],
                        "source_grounded_target_candidate": is_target and grounded,
                        "never_achieved_performance": is_target,
                    }
                )
        valid = [
            o
            for o in observations
            if o["raw_value"] is not None and o["validation_state"] != "rejected"
        ]
        by_company = {
            str(c["id"]): [j for j in jobs if str(j.company_id) == c["id"]]
            for c in run.company_snapshot
        }
        companies = []
        for company in run.company_snapshot:
            cid = str(company["id"])
            cj = by_company[cid]
            values = [o for o in valid if o["company_id"] == cid]
            complete = all(j.status == "succeeded" for j in cj) and bool(values)
            failures = [
                {
                    "stage": j.stage,
                    "metric_id": j.metric_code or None,
                    "status": j.status,
                    "reason_code": j.reason_code,
                    "attempts": j.attempts,
                    "retryable": j.retryable,
                    "details": j.result,
                }
                for j in cj
                if j.status != "succeeded"
            ]
            companies.append(
                {
                    **company,
                    "data_complete": complete,
                    "source_backed_observations": len(values),
                    "failures": failures,
                    "reason_code": (
                        None
                        if complete
                        else (
                            "stage_incomplete"
                            if failures
                            else "no_source_backed_metrics"
                        )
                    ),
                }
            )

        def count_stage(stage: str) -> int:
            return len(
                {
                    j.company_id
                    for j in jobs
                    if j.stage == stage and j.status == "succeeded"
                }
            )

        coverage = {}
        parameters: dict[str, Any] = run.parameters
        for metric in parameters["metrics"]:
            rows = [o for o in valid if o["metric_id"] == metric]
            coverage[metric] = {
                "companies_total": len(companies),
                "companies_with_candidates": len(
                    {
                        j.company_id
                        for j in jobs
                        if j.metric_code == metric
                        and j.stage == "retrieve"
                        and j.result.get("candidates")
                    }
                ),
                "companies_with_observations": len({o["company_id"] for o in rows}),
                "companies_validated": len(
                    {
                        o["company_id"]
                        for o in rows
                        if o["validation_state"] == "validated"
                    }
                ),
                "companies_needing_review": len(
                    {
                        o["company_id"]
                        for o in rows
                        if o["validation_state"] in {"needs_review", "not_comparable"}
                    }
                ),
                "companies_with_review_target_candidates": len(
                    {
                        c["company_id"]
                        for c in candidates
                        if c["metric_id"] == metric
                        and c["source_grounded_target_candidate"]
                    }
                ),
            }
        summary = {
            "companies_total": len(companies),
            "companies_started": len(
                {
                    j.company_id
                    for j in jobs
                    if j.attempts or j.result.get("inherited_from_job_id")
                }
            ),
            "companies_not_started": len(companies)
            - len(
                {
                    j.company_id
                    for j in jobs
                    if j.attempts or j.result.get("inherited_from_job_id")
                }
            ),
            "companies_with_stage_failure": len(
                {
                    j.company_id
                    for j in jobs
                    if j.status in {"failed", "needs_review", "unavailable"}
                }
            ),
            "reports_discovered": count_stage("discover"),
            "downloaded": count_stage("download"),
            "parsed": count_stage("parse"),
            "extracted": len({o["company_id"] for o in valid}),
            "validated": len(
                {o["company_id"] for o in valid if o["validation_state"] == "validated"}
            ),
            "needs_review": len(
                {
                    o["company_id"]
                    for o in observations
                    if o["validation_state"] in {"needs_review", "not_comparable"}
                }
                | {
                    str(j.company_id)
                    for j in jobs
                    if j.status in {"needs_review", "unavailable"}
                }
            ),
            "failed": sum(not c["data_complete"] for c in companies),
            "stage_states": dict(Counter(j.status for j in jobs)),
            "observation_states": dict(
                Counter(o["validation_state"] for o in observations)
            ),
            "checkpoint_passed": len(companies) == run.checkpoint
            and all(c["data_complete"] for c in companies),
            "metric_coverage": coverage,
            "coverage_denominator": "all companies in the frozen checkpoint; missing values never zero",
            "validated_definition": "approved observation state, NOT Pydantic/schema validation",
            "failure_definition": "companies failing strict data-complete checkpoint, including unavailable/review/unfinished stages or no metrics",
        }
        events = list(
            session.scalars(
                select(PipelineEvent)
                .where(PipelineEvent.job_id.in_([j.id for j in jobs]))
                .order_by(PipelineEvent.created_at, PipelineEvent.id)
            )
        )
        return {
            "run_id": str(run.id),
            "checkpoint": run.checkpoint,
            "status": run.status,
            "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
            "requested_year": run.requested_year,
            "observation_year": run.observation_year,
            "parameters": run.parameters,
            "summary": summary,
            "companies": companies,
            "jobs": [
                {
                    "id": str(j.id),
                    "company_id": str(j.company_id),
                    "stage": j.stage,
                    "metric_id": j.metric_code,
                    "status": j.status,
                    "attempts": j.attempts,
                    "retryable": j.retryable,
                    "reason_code": j.reason_code,
                    "result": j.result,
                }
                for j in jobs
            ],
            "events": [
                {
                    "id": str(e.id),
                    "job_id": str(e.job_id),
                    "status": e.status,
                    "attempt": e.attempt,
                    "reason_code": e.reason_code,
                    "created_at": e.created_at.isoformat(),
                    "details": e.details,
                }
                for e in events
            ],
            "observations": observations,
            "candidate_evidence": candidates,
            "extraction_runs": extraction_runs,
        }


def finish(engine: Engine, run_id: UUID) -> dict[str, Any]:
    payload = snapshot(engine, run_id)
    with Session(engine) as session, session.begin():
        run = session.get(PipelineRun, run_id)
        assert run is not None
        run.status = (
            "succeeded" if payload["summary"]["checkpoint_passed"] else "failed"
        )
        run.summary, run.finished_at = payload["summary"], datetime.now(UTC)
        payload["status"] = run.status
    return payload


def safe_csv(value: Any) -> str:
    if value is None:
        return ""
    result = (
        json.dumps(value, ensure_ascii=False)
        if isinstance(value, (dict, list))
        else str(value)
    )
    # Excerpts/company names are untrusted spreadsheet input. JSON remains exact.
    return (
        "'" + result
        if result.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
        else result
    )


def export(payload: dict[str, Any], root: Path) -> Path:
    directory = root / str(payload["run_id"])
    directory.mkdir(parents=True, exist_ok=True)
    name = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
    rows: list[dict[str, Any]] = []
    companies = {c["id"]: c for c in payload["companies"]}
    for obs in payload["observations"]:
        rows.append({"record_kind": "observation", **obs})
    rows.extend(payload["candidate_evidence"])
    # Always export one coverage row per requested company/metric, including
    # missing reports and zero successful values. No silent success-only CSV.
    for company in companies.values():
        company_jobs = [j for j in payload["jobs"] if j["company_id"] == company["id"]]
        report: dict[str, Any] = next(
            (
                j["result"]["report"]
                for stage in ("download", "discover")
                for j in company_jobs
                if j["stage"] == stage and j["result"].get("report")
            ),
            {},
        )
        for metric in payload["parameters"]["metrics"]:
            related = [
                o
                for o in payload["observations"]
                if o["company_id"] == company["id"]
                and o["metric_id"] == metric
                and o["validation_state"] != "rejected"
            ]
            rows.append(
                {
                    "record_kind": "coverage",
                    "company_id": company["id"],
                    "metric_id": metric,
                    "reporting_year": payload["observation_year"],
                    "source_url": report.get("final_url") or report.get("url"),
                    "report_id": report.get("id"),
                    "document_title": report.get("title"),
                    "document_sha256": report.get("sha256"),
                    "official_domain": company["official_domain"],
                    "validation_state": "not_established",
                    "notes": company["reason_code"],
                    "failure_reasons": company["failures"],
                    "observations_count": len(related),
                    "validated_count": sum(
                        o["validation_state"] == "validated" for o in related
                    ),
                    "review_target_candidates_count": sum(
                        c["company_id"] == company["id"]
                        and c["metric_id"] == metric
                        and c["source_grounded_target_candidate"]
                        for c in payload["candidate_evidence"]
                    ),
                }
            )
    for row in rows:
        row.update(
            {
                "pipeline_run_id": payload["run_id"],
                "requested_year": payload["requested_year"],
                "company_name": companies[row["company_id"]]["name"],
            }
        )
    provenance_columns = {
        "pipeline_run_id",
        "company_id",
        "company_name",
        "requested_year",
        "reporting_year",
        "metric_id",
        "raw_value",
        "raw_unit",
        "normalised_value",
        "normalised_unit",
        "source_url",
        "report_id",
        "document_title",
        "document_sha256",
        "physical_page",
        "chunk_id",
        "chunk_sha256",
        "parse_run_id",
        "supporting_excerpt",
        "extraction_run_id",
        "extraction_method",
        "model",
        "model_digest",
        "confidence",
        "validation_state",
        "notes",
        "failure_reasons",
    }
    columns = sorted(provenance_columns | {key for row in rows for key in row})
    for suffix in ("json", "csv"):
        # Atomic publication of completed snapshots; never truncate a prior export.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=directory,
            prefix=".partial-",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            if suffix == "json":
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            else:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerows(
                    {k: safe_csv(v) for k, v in row.items()} for row in rows
                )
            handle.flush()
            os.fsync(handle.fileno())
        target = directory / f"{name}.{suffix}"
        os.link(temporary, target)
        temporary.unlink()
    return directory / f"{name}.json"
