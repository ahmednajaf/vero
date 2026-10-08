"""Bounded, resumable bulk collection. PostgreSQL owns progress; JSON is an export.

This collects source documents, not validated metrics. A completed run may have
explicit gaps. It never stops processing the cohort because one company fails.
"""

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from threading import Semaphore
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    Company,
    KnowledgeJob,
    Report,
    ReportCollection,
    ReportDiscoveryRun,
)
from app.discovery.crawler import SUPPLEMENT
from app.discovery.service import report_dict
from app.knowledge.indexing import index_report
from app.knowledge.ingestion import execute_job, queue, retryable_downloads


def compact(result: dict[str, Any]) -> dict[str, Any]:
    outcome = result.get("outcome", {})
    return {
        "job_id": result["job_id"],
        "status": result["status"],
        "stage": outcome.get("stage"),
        "reason": outcome.get("reason", result.get("reason")),
        "discovery_run_id": outcome.get("discovery_run_id"),
        "reports": [
            {k: v for k, v in r.items() if k != "quality"}
            for r in outcome.get("reports", [])
        ],
    }


def create_collection(
    engine: Engine, ids: list[UUID], year: int, configuration: dict[str, Any]
) -> UUID:
    if not ids or len(ids) > 500 or len(ids) != len(set(ids)):
        raise ValueError("Select 1–500 distinct companies")
    with Session(engine) as session, session.begin():
        found = set(
            session.scalars(
                select(Company.id).where(Company.id.in_(ids), Company.active.is_(True))
            )
        )
        if found != set(ids):
            raise ValueError("Cohort contains unknown or inactive companies")
        row = ReportCollection(
            year=year,
            company_ids=[str(i) for i in ids],
            configuration=configuration,
            results={},
        )
        session.add(row)
        session.flush()
        return row.id


def snapshot(engine: Engine | Connection, run_id: UUID) -> dict[str, Any]:
    with Session(engine) as session:
        run = session.get(ReportCollection, run_id)
        if not run:
            raise ValueError("unknown_collection")
        ids = [UUID(i) for i in run.company_ids]
        companies = list(
            session.scalars(
                select(Company)
                .where(Company.id.in_(ids))
                .order_by(Company.company_name)
            )
        )
        jobs = {
            j.company_id: j
            for j in session.scalars(
                select(KnowledgeJob).where(
                    KnowledgeJob.company_id.in_(ids), KnowledgeJob.year == run.year
                )
            )
        }
        rows = []
        for company in companies:
            job = jobs.get(company.id)
            result = cast(dict[str, Any], run.results.get(str(company.id), {}))
            evidence_outcome: dict[str, Any] = (
                result if result else cast(dict[str, Any], job.outcome) if job else {}
            )
            report_ids = (
                [
                    UUID(r["report_id"])
                    for r in evidence_outcome.get("reports", [])
                    if r.get("report_id")
                ]
                if job
                else []
            )
            if not result and job and job.outcome.get("report_id"):
                report_ids.append(UUID(str(job.outcome["report_id"])))
            reports = (
                list(session.scalars(select(Report).where(Report.id.in_(report_ids))))
                if report_ids
                else []
            )
            last_discovery = (
                session.get(ReportDiscoveryRun, UUID(result["discovery_run_id"]))
                if result.get("discovery_run_id")
                else session.scalar(
                    select(ReportDiscoveryRun)
                    .where(
                        ReportDiscoveryRun.company_id == company.id,
                        ReportDiscoveryRun.requested_year == run.year,
                    )
                    .order_by(
                        ReportDiscoveryRun.created_at.desc(),
                        ReportDiscoveryRun.id.desc(),
                    )
                    .limit(1)
                )
            )
            rows.append(
                {
                    "company_id": str(company.id),
                    "company": company.company_name,
                    "country": company.country,
                    "sector": company.sector,
                    "official_domain": company.official_domain,
                    "status": result.get("status", "pending"),
                    "live_job_status": job.status if job else "pending",
                    "stage": result.get("stage")
                    if result
                    else job.outcome.get("stage")
                    if job
                    else "pending",
                    "result": result,
                    "reports": [
                        {
                            **report_dict(r),
                            "pages": r.page_count,
                            "parse_status": r.parse_status,
                            "document_role": "supporting_document"
                            if SUPPLEMENT.search(r.title + " " + r.source_url)
                            else "primary_report_candidate",
                        }
                        for r in reports
                    ],
                    "discovery_reason": last_discovery.selection_reason
                    if last_discovery
                    else None,
                    "diagnostics": last_discovery.diagnostics if last_discovery else [],
                }
            )
        retained = [
            r for c in rows for r in c["reports"] if r["status"] == "downloaded"
        ]
        summary = {
            "companies": len(ids),
            "processed": len(run.results),
            "remaining": len(ids) - len(run.results),
            "outcomes": dict(Counter(r["status"] for r in rows)),
            "companies_with_download": sum(
                any(r["status"] == "downloaded" for r in c["reports"]) for c in rows
            ),
            "downloaded_reports": len({r["id"] for r in retained}),
            "primary_report_candidates": sum(
                r["document_role"] == "primary_report_candidate" for r in retained
            ),
            "supporting_documents": sum(
                r["document_role"] == "supporting_document" for r in retained
            ),
            "requested_year_reports": sum(
                r["detected_year"] == run.year for r in retained
            ),
            "other_year_reports": sum(
                r["detected_year"] is not None and r["detected_year"] != run.year
                for r in retained
            ),
            "unknown_year_reports": sum(r["detected_year"] is None for r in retained),
            "retained_pdf_pages": sum(r["pages"] or 0 for r in retained),
            "metrics_extracted": 0,
            "ai_calls": 0,
        }
        return {
            "run_id": str(run.id),
            "year": run.year,
            "status": run.status,
            "configuration": run.configuration,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "summary": summary,
            "companies": rows,
            "limitations": [
                "Report collection is not verification of extracted metrics or peer comparability.",
                "A year in the report title is not an established reporting period.",
                "Blocked and unresolved sources remain explicit gaps; no synthetic substitutions.",
            ],
        }


def export_snapshot(engine: Engine, run_id: UUID, directory: Path) -> dict[str, Any]:
    data = snapshot(engine, run_id)
    directory.mkdir(parents=True, exist_ok=True)
    # A read-only status export can overlap a worker checkpoint. Each writer
    # owns its temporary file; readers always see one complete JSON document.
    temporary = directory / f"manifest.{uuid4().hex}.tmp"
    try:
        temporary.write_text(json.dumps(data, indent=2) + "\n")
        temporary.replace(directory / "manifest.json")
    finally:
        temporary.unlink(missing_ok=True)
    return data


def run_collection(engine: Engine, run_id: UUID, settings: Settings) -> dict[str, Any]:
    directory = settings.pipeline_root.parent / "collections" / str(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    with engine.connect() as connection:
        lock = {"key": f"report-collection:{run_id}"}
        if not connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"), lock
        ):
            raise ValueError("collection_already_running")
        connection.commit()
        try:
            with Session(engine) as session, session.begin():
                run = session.get(ReportCollection, run_id)
                if not run:
                    raise ValueError("unknown_collection")
                ids, year = [UUID(i) for i in run.company_ids], run.year
                config = cast(dict[str, Any], dict(run.configuration))
                run.status, run.finished_at = "running", None
                run.started_at = run.started_at or datetime.now(UTC)
            workers, parse_workers = (
                int(config.get("workers", 4)),
                int(config.get("parse_workers", 1)),
            )
            if not 1 <= workers <= 8 or not 1 <= parse_workers <= 2:
                raise ValueError("workers must be 1–8; parse_workers 1–2")
            settings = settings.model_copy(
                update={
                    "discovery_search_fallback": bool(
                        config.get("search_fallback", True)
                    ),
                    "discovery_allow_js": bool(config.get("allow_js", False)),
                    "discovery_max_pages": int(config.get("max_pages", 10)),
                    "discovery_max_requests": 60,
                    "discovery_retries": 1,
                    "discovery_timeout_seconds": 12.0,
                    "discovery_verify_annual_content": True,
                    "discovery_sitemap_fallback": True,
                    "discovery_allow_prior_year": bool(
                        config.get("allow_prior_year", False)
                    ),
                    "discovery_allow_unlabelled_year": bool(
                        config.get("allow_unlabelled_year", False)
                    ),
                }
            )
            jobs = queue(engine, ids, year)
            with Session(engine) as session:
                job_companies = {
                    key: value
                    for key, value in session.execute(
                        select(KnowledgeJob.id, KnowledgeJob.company_id).where(
                            KnowledgeJob.id.in_(jobs)
                        )
                    ).all()
                }
                names = {
                    key: value
                    for key, value in session.execute(
                        select(Company.id, Company.company_name).where(
                            Company.id.in_(ids)
                        )
                    ).all()
                }
            parse_gate = Semaphore(parse_workers)

            def worker(job_id: UUID) -> dict[str, Any]:
                with Session(engine) as session:
                    job = session.get(KnowledgeJob, job_id)
                    assert job
                    primary = []
                    prior_year_source = False
                    for record in cast(
                        list[dict[str, Any]], job.outcome.get("reports", [])
                    ):
                        if record.get("status") in {"indexed", "unchanged"}:
                            report = session.get(Report, UUID(record["report_id"]))
                            if report and not SUPPLEMENT.search(
                                report.title + " " + report.source_url
                            ):
                                primary.append(report.id)
                                prior_year_source = (
                                    prior_year_source or report.detected_year != year
                                )
                    refresh = (
                        job.status
                        in {
                            "succeeded",
                            "partial",
                            "failed",
                            "needs_review",
                            "unavailable",
                        }
                        and not primary
                        and not retryable_downloads(
                            job.outcome,
                            allow_unavailable_robots=settings.discovery_allow_unavailable_robots_for_linked_documents,
                        )
                    )
                if primary:
                    try:
                        # Resume rechecks the retained file and page hashes, not just a status flag.
                        with parse_gate:
                            checks = [
                                index_report(engine, identifier, settings)
                                for identifier in primary
                            ]
                        return {
                            "job_id": str(job_id),
                            "status": "partial"
                            if prior_year_source
                            or any(
                                c.get("quality", {}).get("coverage")
                                == "partial_extracted_text"
                                for c in checks
                            )
                            else "succeeded",
                            "outcome": {"stage": "finished", "reports": checks},
                            "reused": True,
                        }
                    except (ValueError, OSError):
                        refresh = True
                return execute_job(
                    engine,
                    job_id,
                    settings,
                    resume=True,
                    refresh=refresh,
                    retry_failed=True,
                    parse_gate=parse_gate,
                )

            print(
                json.dumps(
                    {
                        "event": "collection_started",
                        "run_id": str(run_id),
                        "companies": len(ids),
                        "workers": workers,
                        "manifest": str(directory / "manifest.json"),
                    }
                ),
                flush=True,
            )
            export_snapshot(engine, run_id, directory)
            with ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="reports"
            ) as pool:
                futures = {pool.submit(worker, job): job for job in jobs}
                for future in as_completed(futures):
                    job_id = futures[future]
                    try:
                        result = compact(future.result())
                    except Exception as exc:
                        result = {
                            "job_id": str(job_id),
                            "status": "failed",
                            "reason": type(exc).__name__,
                            "stage": "worker",
                        }
                    company_id = job_companies[job_id]
                    with Session(engine) as session, session.begin():
                        discovery_id = session.scalar(
                            select(ReportDiscoveryRun.id)
                            .where(
                                ReportDiscoveryRun.company_id == company_id,
                                ReportDiscoveryRun.requested_year == year,
                            )
                            .order_by(
                                ReportDiscoveryRun.created_at.desc(),
                                ReportDiscoveryRun.id.desc(),
                            )
                            .limit(1)
                        )
                        result["discovery_run_id"] = (
                            str(discovery_id) if discovery_id else None
                        )
                        run = session.get(ReportCollection, run_id)
                        assert run
                        run.results = {**run.results, str(company_id): result}
                        processed = len(run.results)
                    event = {
                        "event": "company_finished",
                        "run_id": str(run_id),
                        "company": names[company_id],
                        "company_id": str(company_id),
                        "processed": processed,
                        "total": len(ids),
                        **result,
                    }
                    with (directory / "events.jsonl").open("a") as stream:
                        stream.write(json.dumps(event) + "\n")
                    print(json.dumps(event), flush=True)
                    if processed % 10 == 0 or processed == len(ids):
                        export_snapshot(engine, run_id, directory)
            with Session(engine) as session, session.begin():
                run = session.get(ReportCollection, run_id)
                assert run
                run.status = (
                    "completed"
                    if all(
                        v["status"] == "succeeded"
                        for v in cast(dict[str, Any], run.results).values()
                    )
                    else "completed_with_gaps"
                )
                run.finished_at = datetime.now(UTC)
            return export_snapshot(engine, run_id, directory)
        except BaseException:
            with Session(engine) as session, session.begin():
                run = session.get(ReportCollection, run_id)
                if run:
                    run.status = "interrupted"
            raise
        finally:
            connection.rollback()
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"), lock
            )
            connection.commit()
