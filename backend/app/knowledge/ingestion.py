"""Independent resumable company jobs. One company's failure never blocks the cohort."""

import json
import logging
import re
from contextlib import nullcontext
from threading import Semaphore
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Company, DocumentPage, KnowledgeJob, Report
from app.discovery.crawler import SUPPLEMENT
from app.discovery.http import SafeHTTP
from app.discovery.service import discover_company, download_report, policy_for
from app.knowledge.indexing import index_report
from app.parsing.service import parse_report
from app.pipeline.throttle import DomainPacer

LOG = logging.getLogger(__name__)


def retryable_downloads(
    outcome: dict[str, Any], *, allow_unavailable_robots: bool = False
) -> set[UUID]:
    """Reuse selected candidates after an explicit, applicable policy change.

    This does not approve a source: download_report still restores the exact
    official-page link and checks robots and the document response normally.
    A refusal from the PDF itself is never made retryable by this setting.
    """
    reasons = {
        "Per-company HTTP request budget exhausted",
        "Download refused: expected PDF MIME, received application/x-pdf",
    }
    if allow_unavailable_robots:
        reasons.add("robots.txt returned HTTP 403; stopped conservatively")
    return {
        UUID(r["report_id"])
        for r in outcome.get("reports", [])
        if r.get("report_id")
        and r.get("stage") == "download"
        and r.get("reason") in reasons
    }


def queue(engine: Engine, company_ids: list[UUID], year: int) -> list[UUID]:
    with Session(engine) as session, session.begin():
        for identifier in company_ids:
            session.execute(
                insert(KnowledgeJob)
                .values(company_id=identifier, year=year)
                .on_conflict_do_nothing(index_elements=["company_id", "year"])
            )
        return list(
            session.scalars(
                select(KnowledgeJob.id)
                .where(
                    KnowledgeJob.company_id.in_(company_ids), KnowledgeJob.year == year
                )
                .order_by(KnowledgeJob.id)
            )
        )


def execute_job(
    engine: Engine,
    job_id: UUID,
    settings: Settings,
    *,
    resume: bool = False,
    refresh: bool = False,
    reuse_retained: bool = False,
    source_report_ids: list[UUID] | None = None,
    parse_gate: Semaphore | None = None,
    retry_failed: bool = False,
) -> dict[str, Any]:
    # Session lock survives stage commits and is automatically released on a crash.
    with engine.connect() as connection:
        lock = {"key": "knowledge-job:" + str(job_id)}
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"), lock
        )
        connection.commit()
        if not acquired:
            return {"job_id": str(job_id), "status": "busy"}
        try:
            with Session(connection, expire_on_commit=False) as session:
                job = session.get(KnowledgeJob, job_id)
                if not job:
                    raise ValueError("unknown_knowledge_job")
                if (
                    not refresh
                    and not source_report_ids
                    and job.status != "pending"
                    and (not resume or job.status == "succeeded")
                ):
                    return {
                        "job_id": str(job_id),
                        "status": job.status,
                        "reused": True,
                        "outcome": job.outcome,
                    }
                if (
                    not refresh
                    and not source_report_ids
                    and not retry_failed
                    and job.attempts >= settings.pipeline_job_max_attempts
                ):
                    return {
                        "job_id": str(job_id),
                        "status": job.status,
                        "reason": "attempt_limit_reached",
                    }
                prior_reports: Any = job.outcome.get("reports", [])
                deferred = (
                    retryable_downloads(
                        job.outcome,
                        allow_unavailable_robots=settings.discovery_allow_unavailable_robots_for_linked_documents,
                    )
                    if resume
                    else set()
                )
                retained_ids = (
                    {r.get("report_id") for r in prior_reports} if resume else set()
                )
                if resume and job.outcome.get("report_id"):
                    retained_ids.add(job.outcome["report_id"])
                if source_report_ids:
                    eligible_ids = set(
                        session.scalars(
                            select(Report.id).where(
                                Report.id.in_(source_report_ids),
                                Report.company_id == job.company_id,
                                Report.requested_year == job.year,
                                Report.source_policy == "official",
                                (Report.status == "downloaded")
                                | (
                                    Report.is_selected.is_(True)
                                    & (
                                        (Report.status == "discovered")
                                        | Report.id.in_(deferred)
                                    )
                                ),
                            )
                        )
                    )
                    if eligible_ids != set(source_report_ids):
                        # A stale/wrong explicit ID is a request error, not a new
                        # failed acquisition. Preserve the existing checkpoint.
                        return {
                            "job_id": str(job.id),
                            "status": "failed",
                            "reason": "Explicit reports must be official, selected/downloaded, and belong to this company and cycle",
                            "checkpoint_preserved": True,
                        }
                job.status, job.attempts = "running", job.attempts + 1
                job.outcome = {"stage": "discover", "reports": []}
                session.commit()
                LOG.info(
                    "knowledge_ingest job=%s stage=discover attempt=%s",
                    job.id,
                    job.attempts,
                )
                company = session.get(Company, job.company_id)
                assert company is not None
                policy = policy_for(company, settings)
                http = SafeHTTP(
                    settings, policy, pacer=DomainPacer(engine, policy.domains)
                )
                try:
                    reports = list(
                        session.scalars(
                            select(Report)
                            .where(
                                Report.company_id == company.id,
                                Report.requested_year == job.year,
                                Report.source_policy == "official",
                                (Report.status == "downloaded")
                                | (
                                    (Report.status == "discovered")
                                    & Report.is_selected.is_(True)
                                )
                                # Local budget failures are already-selected official
                                # candidates, not newly approved external sources.
                                | (
                                    Report.id.in_(deferred)
                                    & Report.is_selected.is_(True)
                                ),
                            )
                            .order_by(Report.id)
                        )
                    )
                    if source_report_ids:
                        reports = [r for r in reports if r.id in source_report_ids]
                        if {r.id for r in reports} != set(source_report_ids):
                            raise ValueError(
                                "Explicit reports must be official, selected/downloaded, and belong to this company and cycle"
                            )
                    elif not reuse_retained:
                        reports = [r for r in reports if str(r.id) in retained_ids]
                    if (refresh or not reports) and not source_report_ids:
                        # Reserve part of the same total budget for retrieving
                        # chosen PDFs. An exhaustive link crawl must not leave
                        # zero requests for a source it has already found.
                        http_settings = http.settings
                        reserve = min(12, http_settings.discovery_max_requests // 4)
                        http.settings = http_settings.model_copy(
                            update={
                                "discovery_max_requests": max(
                                    1, http_settings.discovery_max_requests - reserve
                                )
                            }
                        )
                        try:
                            run = discover_company(
                                session, company, job.year, settings, http=http
                            )
                        finally:
                            http.settings = http_settings
                        # Preserve already retained reports even when this refresh fails.
                        discovered = list(
                            session.scalars(
                                select(Report)
                                .where(
                                    Report.discovery_run_id == run.id,
                                    Report.status == "discovered",
                                )
                                .order_by(
                                    Report.is_selected.desc(),
                                    Report.confidence.desc(),
                                    Report.id,
                                )
                                .limit(5)
                            )
                        )
                        reports = list({r.id: r for r in reports + discovered}.values())
                        if not reports:
                            job.status = (
                                run.status
                                if run.status
                                in {"failed", "needs_review", "unavailable"}
                                else "needs_review"
                            )
                            job.outcome = {
                                "stage": "discover",
                                "reason": run.selection_reason,
                                "discovery_run_id": str(run.id),
                            }
                            session.commit()
                            return {
                                "job_id": str(job.id),
                                "status": job.status,
                                "outcome": job.outcome,
                            }
                    outcomes: list[dict[str, Any]] = []
                    seen_hashes: set[str] = set()
                    for report in reports:
                        try:
                            # Do not substitute an assurance statement or policy for a full report.
                            if SUPPLEMENT.search(
                                report.title + " " + report.source_url
                            ):
                                outcomes.append(
                                    {
                                        "report_id": str(report.id),
                                        "status": "needs_review",
                                        "reason": "supporting_document_not_primary",
                                    }
                                )
                                continue
                            job.outcome = {
                                "stage": "download",
                                "report_id": str(report.id),
                                "reports": outcomes,
                            }
                            session.commit()
                            if report.status != "downloaded":
                                # Keep alternatives and try the next eligible PDF when one fails.
                                if not report.is_selected:
                                    for previous in session.scalars(
                                        select(Report).where(
                                            Report.discovery_run_id
                                            == report.discovery_run_id,
                                            Report.is_selected.is_(True),
                                        )
                                    ):
                                        previous.is_selected = False
                                    session.flush()
                                    report.is_selected = True
                                    session.commit()
                                download_reason = download_report(
                                    session, report, company, settings, http=http
                                )
                            else:
                                download_reason = "Already downloaded"
                            if report.status != "downloaded":
                                outcomes.append(
                                    {
                                        "report_id": str(report.id),
                                        "status": report.status,
                                        "stage": "download",
                                        "reason": download_reason,
                                    }
                                )
                                continue
                            if report.content_sha256 in seen_hashes:
                                outcomes.append(
                                    {
                                        "report_id": str(report.id),
                                        "status": "duplicate_artifact",
                                    }
                                )
                                continue
                            seen_hashes.add(report.content_sha256 or "")
                            job.outcome = {
                                "stage": "parse",
                                "report_id": str(report.id),
                                "reports": outcomes,
                            }
                            session.commit()
                            with (
                                parse_gate if parse_gate is not None else nullcontext()
                            ):
                                parsed = parse_report(engine, report.id, settings)
                            if parsed["status"] in {"failed", "busy"}:
                                outcomes.append(
                                    {
                                        "report_id": str(report.id),
                                        "status": parsed["status"],
                                        "stage": "parse",
                                    }
                                )
                                continue
                            if (
                                report.report_type == "annual"
                                and settings.discovery_verify_annual_content
                            ):
                                # An annual-report link need not mention ESG. Inspect
                                # its actual pages, rather than dropping it at discovery.
                                # This is document inclusion, not metric validation.
                                disclosure = re.compile(
                                    r"scope\s*[123]\b|greenhouse\s+gas|sustainability\s+(?:statement|report)|carbon\s+emissions",
                                    re.I,
                                )
                                pages = session.scalars(
                                    select(DocumentPage.raw_text).where(
                                        DocumentPage.report_id == report.id,
                                        DocumentPage.parse_run_id
                                        == UUID(parsed["run_id"]),
                                    )
                                )
                                if not any(disclosure.search(page) for page in pages):
                                    outcomes.append(
                                        {
                                            "report_id": str(report.id),
                                            "status": "needs_review",
                                            "stage": "content_check",
                                            "reason": "annual_report_sustainability_disclosure_not_identified",
                                        }
                                    )
                                    continue
                            job.outcome = {
                                "stage": "index",
                                "report_id": str(report.id),
                                "reports": outcomes,
                            }
                            session.commit()
                            indexed = index_report(engine, report.id, settings)
                            if report.detected_year is None:
                                indexed["unknown_year_source"] = True
                            if (
                                report.detected_year
                                and report.detected_year != job.year
                            ):
                                indexed["prior_year_source"] = True
                                indexed["detected_year"] = report.detected_year
                            outcomes.append(indexed)
                            # One successful primary report is enough for this acquisition cycle.
                            if not source_report_ids and outcomes[-1]["status"] in {
                                "indexed",
                                "unchanged",
                            }:
                                break
                        except (ValueError, OSError) as exc:
                            outcomes.append(
                                {
                                    "report_id": str(report.id),
                                    "status": "failed",
                                    "reason": str(exc)[:300]
                                    if isinstance(exc, ValueError)
                                    else type(exc).__name__,
                                }
                            )
                    ok = [
                        r for r in outcomes if r["status"] in {"indexed", "unchanged"}
                    ]
                    gaps = any(
                        r.get("quality", {}).get("coverage") == "partial_extracted_text"
                        or r.get("prior_year_source")
                        or r.get("unknown_year_source")
                        for r in ok
                    )
                    failures = any(
                        r["status"]
                        not in {"indexed", "unchanged", "duplicate_artifact"}
                        for r in outcomes
                    )
                    job.status = (
                        "partial"
                        if ok and (gaps or failures)
                        else "succeeded"
                        if ok
                        else "failed"
                    )
                    job.outcome = {
                        "stage": "finished",
                        "reports": outcomes,
                        "indexed": len(ok),
                        "ai_called": False,
                    }
                    session.commit()
                    return {
                        "job_id": str(job.id),
                        "status": job.status,
                        "outcome": job.outcome,
                    }
                except Exception as exc:
                    session.rollback()
                    prior_outcome = dict(job.outcome)
                    job.status, job.outcome = (
                        "failed",
                        {
                            **prior_outcome,
                            "failed_at_stage": prior_outcome.get("stage"),
                            "stage": "interrupted",
                            "reason": str(exc)[:300]
                            if isinstance(exc, ValueError)
                            else type(exc).__name__,
                        },
                    )
                    session.commit()
                    return {
                        "job_id": str(job.id),
                        "status": "failed",
                        "outcome": job.outcome,
                    }
                finally:
                    http.close()
        finally:
            connection.rollback()
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"), lock
            )
            connection.commit()


def run_jobs(
    engine: Engine,
    jobs: list[UUID],
    settings: Settings,
    *,
    resume: bool,
    refresh: bool,
    reuse_retained: bool = False,
    source_report_ids: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    outcomes = []
    # Deliberately one worker on the development laptop. DB locks support safe resume.
    for job_id in jobs:
        result = execute_job(
            engine,
            job_id,
            settings,
            resume=resume,
            refresh=refresh,
            reuse_retained=reuse_retained,
            source_report_ids=source_report_ids,
        )
        outcomes.append(result)
        print(json.dumps({"event": "knowledge_ingestion", **result}), flush=True)
    return outcomes
